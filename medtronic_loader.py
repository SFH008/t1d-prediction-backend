#!/usr/bin/env python3
"""
Medtronic Export → PostgreSQL T1D Database Loader
Robust data pipeline with validation, deduplication, and transactional safety

Usage:
    python medtronic_loader.py <json_export_file> [--db-uri postgresql://user:pass@host/db]
"""

import json
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
import uuid
from decimal import Decimal

import psycopg2
from psycopg2.extras import execute_values
from psycopg2.errors import IntegrityError, UniqueViolation

# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_DB_URI = "postgresql://t1d_app_user:password@localhost:5432/t1d_glucose_forecasting"
GLUCOSE_THRESHOLD_HYPO = 70
GLUCOSE_THRESHOLD_SEVERE_HYPO = 54
GLUCOSE_THRESHOLD_HYPER = 180
GLUCOSE_THRESHOLD_SEVERE_HYPER = 250

# Medtronic marker types to extract
INSULIN_MARKER_TYPES = {
    "MANUAL_BOLUS_DELIVERY",
    "AUTO_BASAL_DELIVERY",
    "REWIND",
    "FILL",
    "SUSPEND",
}

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("medtronic_loader.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES & VALIDATION
# ============================================================================


class ValidationError(Exception):
    """Custom exception for data validation failures."""
    pass


class MedtronicLoader:
    """Main loader class handling extraction, validation, and database insertion."""

    def __init__(self, json_file: str, db_uri: str = DEFAULT_DB_URI):
        self.json_file = Path(json_file)
        self.db_uri = db_uri
        self.conn = None
        self.cursor = None
        self.import_log_id = None
        self.import_stats = {
            "glucose_count": 0,
            "insulin_count": 0,
            "therapy_limits_count": 0,
            "duplicates_skipped": 0,
            "errors": [],
        }

    def connect(self):
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(self.db_uri)
            self.cursor = self.conn.cursor()
            logger.info("✓ Connected to PostgreSQL")
        except Exception as e:
            logger.error(f"✗ Database connection failed: {e}")
            raise

    def disconnect(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("✓ Disconnected from PostgreSQL")

    def load_json(self) -> Dict:
        """Load and parse Medtronic JSON export."""
        try:
            with open(self.json_file, "r") as f:
                data = json.load(f)
            logger.info(f"✓ Loaded JSON from {self.json_file.name}")
            return data
        except Exception as e:
            logger.error(f"✗ Failed to load JSON: {e}")
            raise

    def validate_glucose_value(self, glucose_mg_dl: float) -> bool:
        """Validate glucose reading is in physiologically plausible range."""
        return 40 <= glucose_mg_dl <= 400

    def validate_insulin_amount(self, amount: float) -> bool:
        """Validate insulin amount is reasonable."""
        return 0 <= amount <= 100

    def classify_glucose_flags(self, glucose_mg_dl: float) -> Dict[str, bool]:
        """Classify glucose reading into hypo/hyper buckets."""
        return {
            "is_hypo": glucose_mg_dl < GLUCOSE_THRESHOLD_HYPO,
            "is_severe_hypo": glucose_mg_dl < GLUCOSE_THRESHOLD_SEVERE_HYPO,
            "is_hyper": glucose_mg_dl > GLUCOSE_THRESHOLD_HYPER,
            "is_severe_hyper": glucose_mg_dl > GLUCOSE_THRESHOLD_SEVERE_HYPER,
        }

    def extract_trend_arrow(self, trend_str: str) -> Optional[str]:
        """Map Medtronic trend string to Unicode arrow."""
        trend_map = {
            "UP": "↑",
            "UP_UP": "↑↑",
            "UP_SLIGHT": "↗",
            "FLAT": "→",
            "DOWN_SLIGHT": "↘",
            "DOWN": "↓",
            "DOWN_DOWN": "↓↓",
            "NONE": None,
            "NOT_AVAILABLE": None,
        }
        return trend_map.get(trend_str.upper())

    def get_or_create_patient(self, patient_data: Dict) -> uuid.UUID:
        """
        Get existing patient by device serial, or create new patient.
        Returns patient UUID.
        """
        device_serial = patient_data.get("medicalDeviceInformation", {}).get("deviceSerialNumber")
        if not device_serial:
            raise ValidationError("Missing deviceSerialNumber in export")

        # Check if patient exists
        self.cursor.execute(
            "SELECT id FROM patients WHERE external_patient_id = %s LIMIT 1",
            (device_serial,),
        )
        result = self.cursor.fetchone()
        if result:
            patient_id = result[0]
            logger.info(f"  Found existing patient: {patient_id}")
            return patient_id

        # Create new patient
        patient_id = uuid.uuid4()
        first_name = patient_data.get("firstName", "Unknown").split()[-1]  # Last name
        last_name = patient_data.get("lastName", "Unknown").split()[0]  # First name
        tz = patient_data.get("clientTimeZoneName", "UTC")

        try:
            self.cursor.execute(
                """
                INSERT INTO patients (
                    id, external_patient_id, first_name, last_name,
                    date_of_birth, sex, diabetes_type, diagnosis_date, time_zone,
                    is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    patient_id,
                    device_serial,
                    first_name,
                    last_name,
                    datetime(2000, 1, 1).date(),  # Placeholder
                    None,
                    "type_1",
                    None,
                    tz,
                    True,
                ),
            )
            logger.info(f"  Created new patient: {patient_id} ({first_name} {last_name})")
        except IntegrityError as e:
            self.conn.rollback()
            logger.error(f"  Integrity error creating patient: {e}")
            raise

        return patient_id

    def update_patient_device_status(self, patient_id: uuid.UUID, patient_data: Dict):
        """Update patient's pump/sensor status and last sync times."""
        try:
            pump_battery = patient_data.get("pumpBatteryLevelPercent")
            sensor_battery = patient_data.get("gstBatteryLevel")
            last_conduit = patient_data.get("lastConduitDateTime")
            last_medical_device = patient_data.get("lastMedicalDeviceDataUpdateServerTime")

            # Determine statuses
            pump_status = "connected" if patient_data.get("pumpCommunicationState") else "disconnected"
            sensor_status = "active" if patient_data.get("gstCommunicationState") else "disconnected"

            self.cursor.execute(
                """
                UPDATE patients SET
                    pump_battery_percent = %s,
                    sensor_battery_percent = %s,
                    pump_status = %s,
                    sensor_status = %s,
                    last_pump_sync = %s,
                    last_sensor_sync = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    Decimal(pump_battery) if pump_battery else None,
                    Decimal(sensor_battery) if sensor_battery else None,
                    pump_status,
                    sensor_status,
                    last_conduit,
                    last_medical_device,
                    patient_id,
                ),
            )
        except Exception as e:
            logger.warning(f"  Failed to update device status: {e}")

    def load_glucose_readings(
        self, patient_id: uuid.UUID, sensor_glucose_data: List[Dict]
    ) -> int:
        """Load sensor glucose readings (SG entries)."""
        count = 0
        duplicates = 0

        for entry in sensor_glucose_data:
            if entry.get("kind") != "SG":
                continue

            try:
                sg_value = entry.get("sg")
                timestamp = entry.get("timestamp")
                sensor_state = entry.get("sensorState", "NO_ERROR_MESSAGE")

                if not sg_value or not timestamp:
                    logger.debug(f"  Skipping incomplete SG entry: {entry}")
                    continue

                if not self.validate_glucose_value(float(sg_value)):
                    logger.warning(f"  Invalid glucose value {sg_value} at {timestamp}")
                    self.import_stats["errors"].append(
                        f"Invalid glucose {sg_value} at {timestamp}"
                    )
                    continue

                # Classify thresholds
                flags = self.classify_glucose_flags(float(sg_value))

                reading_id = uuid.uuid4()
                self.cursor.execute(
                    """
                    INSERT INTO glucose_readings (
                        id, patient_id, glucose_value_mg_dl, timestamp,
                        reading_type, source, is_valid,
                        is_hypo, is_severe_hypo, is_hyper, is_severe_hyper,
                        sensor_state, recorded_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        reading_id,
                        patient_id,
                        Decimal(sg_value),
                        timestamp,
                        "cgm",  # Medtronic CGM
                        "medtronic_export",
                        True,
                        flags["is_hypo"],
                        flags["is_severe_hypo"],
                        flags["is_hyper"],
                        flags["is_severe_hyper"],
                        sensor_state,
                    ),
                )
                count += 1

            except UniqueViolation:
                duplicates += 1
                self.conn.rollback()
                logger.debug(f"  Duplicate glucose reading: {timestamp}")
            except Exception as e:
                self.conn.rollback()
                logger.error(f"  Error loading glucose entry {entry}: {e}")
                self.import_stats["errors"].append(f"Glucose load error: {e}")

        self.import_stats["glucose_count"] = count
        self.import_stats["duplicates_skipped"] += duplicates
        logger.info(f"  ✓ Loaded {count} glucose readings ({duplicates} duplicates skipped)")
        return count

    def load_insulin_events(self, patient_id: uuid.UUID, markers: List[Dict]) -> int:
        """Extract insulin delivery events from markers."""
        count = 0

        for marker in markers:
            marker_type = marker.get("type")
            if marker_type not in INSULIN_MARKER_TYPES:
                continue

            try:
                timestamp = marker.get("timestamp")
                data_values = marker.get("data", {}).get("dataValues", {})

                if not timestamp:
                    continue

                # Parse insulin amounts
                bolus_amount = data_values.get("bolusAmount")
                max_auto_basal = data_values.get("maxAutoBasalRate")

                # Determine insulin type
                if marker_type == "MANUAL_BOLUS_DELIVERY":
                    insulin_type = "bolus"
                elif marker_type == "AUTO_BASAL_DELIVERY":
                    insulin_type = "basal"
                elif marker_type == "REWIND":
                    insulin_type = "rewind"
                elif marker_type == "FILL":
                    insulin_type = "fill"
                elif marker_type == "SUSPEND":
                    insulin_type = "suspend"
                else:
                    insulin_type = "other"

                # Build record
                event_id = uuid.uuid4()
                dose = Decimal(bolus_amount) if bolus_amount else Decimal(0)

                if dose < 0 or dose > 100:
                    logger.warning(f"  Invalid insulin amount {dose} at {timestamp}")
                    continue

                self.cursor.execute(
                    """
                    INSERT INTO insulin_events (
                        id, patient_id, insulin_type, dose_units, timestamp,
                        delivery_method, source, recorded_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        event_id,
                        patient_id,
                        insulin_type,
                        dose,
                        timestamp,
                        "pump",
                        "medtronic_export",
                    ),
                )
                count += 1

            except UniqueViolation:
                self.conn.rollback()
                logger.debug(f"  Duplicate insulin event: {timestamp}")
            except Exception as e:
                self.conn.rollback()
                logger.error(f"  Error loading insulin event {marker}: {e}")
                self.import_stats["errors"].append(f"Insulin load error: {e}")

        self.import_stats["insulin_count"] = count
        logger.info(f"  ✓ Loaded {count} insulin events")
        return count

    def load_therapy_limits(self, patient_id: uuid.UUID, limits: List[Dict]) -> int:
        """Load therapy target ranges."""
        count = 0

        for limit in limits:
            try:
                timestamp = limit.get("timestamp")
                low_limit = limit.get("lowLimit")
                high_limit = limit.get("highLimit")

                if not all([timestamp, low_limit, high_limit]):
                    continue

                limit_id = uuid.uuid4()
                self.cursor.execute(
                    """
                    INSERT INTO therapy_limits (
                        id, patient_id, limit_type, lower_bound, upper_bound,
                        is_hard_limit, created_at, updated_at, is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s)
                    """,
                    (
                        limit_id,
                        patient_id,
                        "glucose_target",
                        Decimal(low_limit),
                        Decimal(high_limit),
                        True,
                        True,
                    ),
                )
                count += 1

            except UniqueViolation:
                self.conn.rollback()
            except Exception as e:
                self.conn.rollback()
                logger.error(f"  Error loading therapy limit {limit}: {e}")

        self.import_stats["therapy_limits_count"] = count
        logger.info(f"  ✓ Loaded {count} therapy limits")
        return count

    def create_import_log(
        self, patient_id: uuid.UUID, file_name: str, start_time: datetime
    ) -> uuid.UUID:
        """Create data_import_logs entry."""
        import_log_id = uuid.uuid4()

        try:
            self.cursor.execute(
                """
                INSERT INTO data_import_logs (
                    id, patient_id, import_source, file_name,
                    import_start_time, glucose_records_count,
                    insulin_records_count, import_status,
                    data_quality_score, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    import_log_id,
                    patient_id,
                    "medtronic_minimed",
                    file_name,
                    start_time,
                    self.import_stats["glucose_count"],
                    self.import_stats["insulin_count"],
                    "PENDING",
                    Decimal(0.95),  # Placeholder quality score
                ),
            )
        except Exception as e:
            logger.error(f"  Failed to create import log: {e}")

        return import_log_id

    def finalize_import_log(self, import_log_id: uuid.UUID, status: str):
        """Update import log with final status."""
        try:
            error_msg = " | ".join(self.import_stats["errors"][:5]) if self.import_stats["errors"] else None

            self.cursor.execute(
                """
                UPDATE data_import_logs SET
                    import_end_time = CURRENT_TIMESTAMP,
                    import_status = %s,
                    total_records_imported = %s,
                    error_message = %s
                WHERE id = %s
                """,
                (
                    status,
                    (
                        self.import_stats["glucose_count"]
                        + self.import_stats["insulin_count"]
                        + self.import_stats["therapy_limits_count"]
                    ),
                    error_msg,
                    import_log_id,
                ),
            )
        except Exception as e:
            logger.error(f"  Failed to finalize import log: {e}")

    def run(self):
        """Execute full import pipeline."""
        start_time = datetime.now(timezone.utc)

        try:
            logger.info("=" * 70)
            logger.info("MEDTRONIC EXPORT LOADER")
            logger.info("=" * 70)

            # Connect and load data
            self.connect()
            data = self.load_json()
            patient_data = data.get("patientData", {})

            # Extract structured data
            sensor_glucose_data = patient_data.get("sensorGlucoseData", [])
            markers = patient_data.get("markers", [])
            limits = patient_data.get("limits", [])

            logger.info(f"\nExport contains:")
            logger.info(f"  - {len(sensor_glucose_data)} sensor glucose entries")
            logger.info(f"  - {len(markers)} marker events")
            logger.info(f"  - {len(limits)} therapy limits")

            # Get or create patient
            logger.info(f"\n[PATIENT]")
            patient_id = self.get_or_create_patient(patient_data)
            self.update_patient_device_status(patient_id, patient_data)

            # Load data
            logger.info(f"\n[GLUCOSE READINGS]")
            self.load_glucose_readings(patient_id, sensor_glucose_data)

            logger.info(f"\n[INSULIN EVENTS]")
            self.load_insulin_events(patient_id, markers)

            logger.info(f"\n[THERAPY LIMITS]")
            self.load_therapy_limits(patient_id, limits)

            # Create and finalize import log
            logger.info(f"\n[IMPORT LOG]")
            import_log_id = self.create_import_log(
                patient_id, self.json_file.name, start_time
            )

            # Commit transaction
            self.conn.commit()
            self.finalize_import_log(import_log_id, "SUCCESS")
            self.conn.commit()

            # Summary
            logger.info(f"\n{'=' * 70}")
            logger.info(f"IMPORT COMPLETE ✓")
            logger.info(f"{'=' * 70}")
            logger.info(f"Patient ID:           {patient_id}")
            logger.info(f"Glucose Readings:     {self.import_stats['glucose_count']}")
            logger.info(f"Insulin Events:       {self.import_stats['insulin_count']}")
            logger.info(f"Therapy Limits:       {self.import_stats['therapy_limits_count']}")
            logger.info(f"Duplicates Skipped:   {self.import_stats['duplicates_skipped']}")
            if self.import_stats["errors"]:
                logger.info(f"Errors Encountered:   {len(self.import_stats['errors'])}")
                for err in self.import_stats["errors"][:3]:
                    logger.info(f"  - {err}")
            logger.info(f"{'=' * 70}\n")

        except Exception as e:
            logger.error(f"\n✗ IMPORT FAILED: {e}")
            self.conn.rollback()
            raise

        finally:
            self.disconnect()


# ============================================================================
# MAIN
# ============================================================================


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Load Medtronic export JSON into T1D PostgreSQL database"
    )
    parser.add_argument("json_file", help="Path to Medtronic export JSON file")
    parser.add_argument(
        "--db-uri",
        default=DEFAULT_DB_URI,
        help=f"PostgreSQL connection URI (default: {DEFAULT_DB_URI})",
    )

    args = parser.parse_args()

    loader = MedtronicLoader(args.json_file, args.db_uri)
    loader.run()


if __name__ == "__main__":
    main()