"""
Data import endpoints.
POST /api/import/medtronic - Upload and process Medtronic JSON export
GET /api/import/{import_id} - Get import status
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from datetime import datetime
import json
import logging

from app.database import get_db
from app.models import (
    Patient, DataImportLog, GlucoseReading, InsulinEvent, TherapyLimit
)
from app.schema.schemas import DataImportResponse, ImportStatusResponse
from decimal import Decimal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/import", tags=["Import"])


@router.post("/medtronic", response_model=ImportStatusResponse, status_code=202)
async def import_medtronic_export(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload and process Medtronic export JSON.

    Args:
        file: Medtronic JSON export file
        db: Database session

    Returns:
        Import status with ID for tracking
    """
    try:
        # Read JSON file
        content = await file.read()
        data = json.loads(content.decode())

        # Extract patient and medical-device data
        patient_data = data.get("patientData", {})
        medical_device = patient_data.get("medicalDeviceInformation", {})

        device_serial = medical_device.get("deviceSerialNumber")
        device_model = medical_device.get("modelNumber")

        if not device_serial:
            raise HTTPException(
                status_code=400,
                detail="Missing patientData.medicalDeviceInformation.deviceSerialNumber"
            )

        # Get or create patient.
        #
        # IMPORTANT:
        #   patients.id is the internal database UUID.
        #   external_patient_id is the stable identifier supplied by the
        #   Medtronic export. Layer 1 resolves this value to patients.id.
        stmt = select(Patient).where(
            Patient.external_patient_id == device_serial
        )
        result = await db.execute(stmt)
        patient = result.scalar_one_or_none()

        if not patient:
            patient = Patient(
                external_patient_id=device_serial,
                first_name=patient_data.get("firstName", ""),
                last_name=patient_data.get("lastName", ""),
                time_zone=patient_data.get("clientTimeZoneName", "UTC"),
                is_active=True,
            )
            db.add(patient)
            await db.flush()

            logger.info(
                "Created patient: id=%s external_patient_id=%s",
                patient.id,
                patient.external_patient_id,
            )

        # Store the actual Medtronic device/CGM information.
        patient.device_serial_number = device_serial
        patient.device_model = device_model
        patient.reservoir_remaining_units = patient_data.get(
            "reservoirRemainingUnits"
        )
        patient.sensor_state = patient_data.get("sensorState")
        patient.calibration_status = patient_data.get("calibStatus")
        patient.sensor_duration_hours = patient_data.get(
            "sensorDurationHours"
        )

        # Store current device status.
        patient.pump_battery_percent = patient_data.get(
            "pumpBatteryLevelPercent"
        )
        patient.sensor_battery_percent = patient_data.get(
            "gstBatteryLevel"
        )

        patient.pump_status = (
            "connected"
            if patient_data.get("pumpCommunicationState")
            else "disconnected"
        )

        patient.sensor_status = (
            "active"
            if patient_data.get("gstCommunicationState")
            else "disconnected"
        )

        patient.last_pump_sync = (
            datetime.fromisoformat(patient_data["lastConduitDateTime"].replace("Z", "+00:00"))
            if patient_data.get("lastConduitDateTime")
            else None
        )
        patient.last_sensor_sync = (
            datetime.fromisoformat(patient_data["lastGstDateTime"].replace("Z", "+00:00"))
            if patient_data.get("lastGstDateTime")
            else None
)

        db.add(patient)
        await db.commit()

        # Create import log
        import_log = DataImportLog(
            patient_id=patient.id,
            import_source="medtronic_minimed",
            device_type="MMT-1886",  # Medtronic 780G
            file_name=file.filename,
            import_start_time=datetime.utcnow(),
            import_status="PROCESSING"
        )
        db.add(import_log)
        await db.commit()
        await db.refresh(import_log)

        # Process glucose readings
        glucose_count = 0
        sensor_glucose_data = patient_data.get("sgs", [])

        for entry in sensor_glucose_data:
            if entry.get("kind") != "SG":
                continue

            try:
                sg_value = entry.get("sg")
                timestamp = entry.get("timestamp")

                if not sg_value or not timestamp:
                    continue

                # Validate
                if not (40 <= float(sg_value) <= 400):
                    logger.warning(f"Invalid glucose {sg_value}")
                    continue

                # Classify
                is_hypo = float(sg_value) < 70
                is_severe_hypo = float(sg_value) < 54
                is_hyper = float(sg_value) > 180
                is_severe_hyper = float(sg_value) > 250

                reading = GlucoseReading(
                    patient_id=patient.id,
                    glucose_value_mg_dl=Decimal(str(sg_value)),
                    timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
                    reading_type="cgm",
                    source="medtronic_export",
                    is_valid=True,
                    is_hypo=is_hypo,
                    is_severe_hypo=is_severe_hypo,
                    is_hyper=is_hyper,
                    is_severe_hyper=is_severe_hyper,
                )
                db.add(reading)
                glucose_count += 1

            except Exception as e:
                logger.error(f"Error processing glucose entry: {e}")
                continue

        # Process insulin events
        insulin_count = 0
        markers = patient_data.get("markers", [])
        insulin_type_map = {
            "MANUAL_BOLUS_DELIVERY": "bolus",
            "AUTO_BASAL_DELIVERY": "basal",
            "REWIND": "rewind",
            "FILL": "fill",
            "SUSPEND": "suspend"
        }

        for marker in markers:
            marker_type = marker.get("type")
            if marker_type not in insulin_type_map:
                continue

            try:
                timestamp = marker.get("timestamp")
                data_values = marker.get("data", {}).get("dataValues", {})

                if not timestamp:
                    continue

                dose = data_values.get("bolusAmount", 0)

                if not (0 <= float(dose) <= 100):
                    logger.warning(f"Invalid insulin amount {dose}")
                    continue

                event = InsulinEvent(
                    patient_id=patient.id,
                    insulin_type=insulin_type_map[marker_type],
                    dose_units=Decimal(str(dose)),
                    timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
                    delivery_method="pump",
                    source="medtronic_export"
                )
                db.add(event)
                insulin_count += 1

            except Exception as e:
                logger.error(f"Error processing insulin event: {e}")
                continue

        # Process therapy limits
        limits_count = 0
        limits = patient_data.get("limits", [])

        for limit in limits:
            try:
                timestamp = limit.get("timestamp")
                low_limit = limit.get("lowLimit")
                high_limit = limit.get("highLimit")

                if not all([timestamp, low_limit, high_limit]):
                    continue

                therapy_limit = TherapyLimit(
                    patient_id=patient.id,
                    limit_type="glucose_target",
                    lower_bound=Decimal(str(low_limit)),
                    upper_bound=Decimal(str(high_limit)),
                    is_hard_limit=True,
                    is_active=True
                )
                db.add(therapy_limit)
                limits_count += 1

            except Exception as e:
                logger.error(f"Error processing therapy limit: {e}")
                continue

        # Commit all data
        await db.commit()

        # Update import log
        import_log.import_end_time = datetime.utcnow()
        import_log.glucose_records_count = glucose_count
        import_log.insulin_records_count = insulin_count
        import_log.carb_records_count = 0
        import_log.total_records_imported = glucose_count + insulin_count + limits_count
        import_log.import_status = "SUCCESS"
        import_log.data_quality_score = Decimal("0.95")

        db.add(import_log)
        await db.commit()

        logger.info(f"✅ Import complete: {glucose_count} glucose, {insulin_count} insulin, {limits_count} limits")

        return ImportStatusResponse(
            import_id=import_log.id,
            status="SUCCESS",
            patient_id=patient.id,
            glucose_count=glucose_count,
            insulin_count=insulin_count,
            error_message=None
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/{import_id}", response_model=DataImportResponse)
async def get_import_status(
    import_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get status of a data import.

    Args:
        import_id: Import log UUID
        db: Database session

    Returns:
        Import status and statistics
    """
    stmt = select(DataImportLog).where(DataImportLog.id == import_id)
    result = await db.execute(stmt)
    import_log = result.scalar_one_or_none()

    if not import_log:
        raise HTTPException(status_code=404, detail=f"Import {import_id} not found")

    return import_log