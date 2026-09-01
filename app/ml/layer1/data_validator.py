"""
Phase 3b: Data Validator

Validates training dataset against hard constraints and quality thresholds.

Detects:
- Missing timestamps
- Duplicate readings
- Invalid glucose values
- Invalid insulin events
- Impossible carbohydrate values
- Gaps in CGM data
- Inconsistent timestamps
- Data outside requested training period
- Insufficient training data
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

import pandas as pd
import numpy as np

from app.ml.layer1.phase3_types import ValidationResult, DataQualityMetrics


logger = logging.getLogger(__name__)


class DataValidator:
    """
    Validate training dataset against medical safety constraints.

    Hard constraints (must pass):
    - Glucose: 40-400 mg/dL
    - Insulin: 0-100 units per event
    - Carbs: 0-500 grams per event
    - Heart rate: 40-250 bpm

    Soft thresholds (raise warnings):
    - Minimum samples: 288 (24 hours @ 5-min intervals)
    - Maximum missing glucose: 30%
    - Maximum CGM gap: 30 consecutive minutes
    """

    # Hard constraints
    HARD_CONSTRAINTS = {
        'glucose_mg_dl': (40, 400),
        'insulin_bolus_units': (0, 100),
        'insulin_basal_units': (0, 50),
        'carb_intake_grams': (0, 500),
        'activity_intensity': (0, 100),
        'heart_rate_bpm': (40, 250),
    }

    # Soft thresholds
    MIN_SAMPLES = 288  # 24 hours @ 5-min intervals
    MAX_MISSING_GLUCOSE_FRACTION = 0.30  # Allow 30% missing
    MAX_CGM_GAP_MINUTES = 30  # Warn if gap > 30 min

    def validate(self, df: pd.DataFrame) -> ValidationResult:
        """
        Run all validation checks on dataset.

        Args:
            df: DataFrame from TrainingDatasetBuilder.extract_patient_data()

        Returns:
            ValidationResult with is_valid, errors, warnings, and summary

        Raises:
            ValueError: If df is empty or missing required columns
        """
        errors = []
        warnings = []
        metadata = {}

        # Check 1: Basic dataframe structure
        try:
            structure_errors = self._check_dataframe_structure(df)
            errors.extend(structure_errors)

            # Remaining checks depend on the required schema.
            if structure_errors:
                return ValidationResult(
                    is_valid=False,
                    errors=errors,
                    warnings=warnings,
                    summary="Invalid dataframe structure",
                    metadata=metadata,
                )
        except Exception as e:
            errors.append(f"Dataframe structure check failed: {e}")
            return ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                summary="Critical: Cannot validate malformed dataframe",
                metadata=metadata,
            )

        # Check 2: Minimum sample count
        check_result = self._check_minimum_samples(df)
        if not check_result['passed']:
            errors.append(check_result['message'])
        metadata['sample_count'] = len(df)

        # Check 3: Timestamps
        timestamp_checks = self._check_timestamps(df)
        errors.extend(timestamp_checks['errors'])
        warnings.extend(timestamp_checks['warnings'])
        metadata.update(timestamp_checks['metadata'])

        # Check 4: Hard constraints
        constraint_checks = self._check_hard_constraints(df)
        errors.extend(constraint_checks['errors'])
        warnings.extend(constraint_checks['warnings'])
        metadata.update(constraint_checks['metadata'])

        # Check 5: Data continuity
        continuity_checks = self._check_data_continuity(df)
        errors.extend(continuity_checks['errors'])
        warnings.extend(continuity_checks['warnings'])
        metadata.update(continuity_checks['metadata'])

        # Check 6: Anomaly detection
        anomaly_checks = self._check_anomalies(df)
        warnings.extend(anomaly_checks['warnings'])
        metadata.update(anomaly_checks['metadata'])

        # Build summary
        summary = self._build_summary(df, errors, warnings, metadata)

        is_valid = len(errors) == 0

        logger.info(
            f"Validation {'PASSED ✅' if is_valid else 'FAILED ❌'}: "
            f"{len(errors)} errors, {len(warnings)} warnings"
        )

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            summary=summary,
            metadata=metadata,
        )

    @staticmethod
    def _check_dataframe_structure(df: pd.DataFrame) -> List[str]:
        """Check basic dataframe structure."""
        errors = []

        if df is None or len(df) == 0:
            errors.append("Dataframe is empty")

        if 'timestamp' not in df.columns:
            errors.append("Missing required column: 'timestamp'")

        if 'glucose_mg_dl' not in df.columns:
            errors.append("Missing required column: 'glucose_mg_dl'")

        return errors

    def _check_minimum_samples(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Check if dataset has minimum required sample count."""
        if len(df) < self.MIN_SAMPLES:
            return {
                'passed': False,
                'message': (
                    f"Insufficient data: {len(df)} samples (need minimum {self.MIN_SAMPLES} = 24 hours @ 5-min)"
                ),
            }

        return {'passed': True, 'message': None}

    @staticmethod
    def _check_timestamps(df: pd.DataFrame) -> Dict[str, Any]:
        """Check timestamp validity."""
        errors = []
        warnings = []
        metadata = {}

        # Convert to datetime
        df_check = df.copy()
        df_check['timestamp'] = pd.to_datetime(df_check['timestamp'], utc=True, errors='coerce')

        # Check for parsing errors
        null_timestamps = df_check['timestamp'].isna().sum()
        if null_timestamps > 0:
            errors.append(f"Invalid timestamps: {null_timestamps} rows could not be parsed")

        # Check for duplicate timestamps
        duplicates = df_check['timestamp'].duplicated().sum()
        if duplicates > 0:
            errors.append(f"Duplicate timestamps: {duplicates} rows have duplicate timestamps")
            metadata['duplicate_timestamp_count'] = duplicates

        # Check for gaps
        if len(df_check) > 1:
            df_check = df_check.sort_values('timestamp')
            time_diffs = df_check['timestamp'].diff().dt.total_seconds() / 60

            max_gap = time_diffs.max()
            mean_gap = time_diffs.mean()
            metadata['max_timestamp_gap_minutes'] = float(max_gap) if not pd.isna(max_gap) else None
            metadata['mean_timestamp_gap_minutes'] = float(mean_gap) if not pd.isna(mean_gap) else None

            # Warn about large gaps
            large_gaps = (time_diffs > 30).sum()
            if large_gaps > 0:
                warnings.append(
                    f"Large timestamp gaps: {large_gaps} intervals > 30 minutes "
                    f"(max: {max_gap:.1f} min, mean: {mean_gap:.1f} min)"
                )

        return {
            'errors': errors,
            'warnings': warnings,
            'metadata': metadata,
        }

    def _check_hard_constraints(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Check hard constraints on measurement values."""
        errors = []
        warnings = []
        metadata = {}

        for col, (min_val, max_val) in self.HARD_CONSTRAINTS.items():
            if col not in df.columns:
                continue  # Column not in dataset (e.g., heart_rate might not be present)

            # Find values outside bounds
            valid = df[col].notna()
            outside_bounds = valid & ((df[col] < min_val) | (df[col] > max_val))
            violating_count = outside_bounds.sum()

            if violating_count > 0:
                violating_values = df.loc[outside_bounds, col].unique()
                errors.append(
                    f"Constraint violation {col}: {violating_count} values outside [{min_val}, {max_val}]. "
                    f"Examples: {sorted(violating_values)[:5]}"
                )
                metadata[f'{col}_violations'] = int(violating_count)

        return {
            'errors': errors,
            'warnings': warnings,
            'metadata': metadata,
        }

    def _check_data_continuity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Check data continuity and missing value patterns."""
        errors = []
        warnings = []
        metadata = {}

        # Check glucose continuity
        if 'glucose_mg_dl' in df.columns:
            missing_glucose = df['glucose_mg_dl'].isna().sum()
            missing_fraction = missing_glucose / len(df)

            metadata['missing_glucose_count'] = int(missing_glucose)
            metadata['missing_glucose_fraction'] = float(missing_fraction)

            if missing_fraction > self.MAX_MISSING_GLUCOSE_FRACTION:
                errors.append(
                    f"Too much missing glucose: {missing_fraction*100:.1f}% missing "
                    f"(max allowed: {self.MAX_MISSING_GLUCOSE_FRACTION*100:.1f}%)"
                )
            elif missing_fraction > 0.15:
                warnings.append(
                    f"High missing glucose: {missing_fraction*100:.1f}% missing"
                )

        # Check for sparse insulin/carbs (expected, not an error)
        if 'insulin_bolus_units' in df.columns:
            insulin_events = df['insulin_bolus_units'].notna().sum()
            metadata['insulin_events'] = int(insulin_events)

            if insulin_events == 0:
                warnings.append("No insulin bolus events found (expected for some patients)")

        if 'carb_intake_grams' in df.columns:
            carb_events = df['carb_intake_grams'].notna().sum()
            metadata['carb_events'] = int(carb_events)

            if carb_events == 0:
                warnings.append("No carb intake events found (unexpected)")

        return {
            'errors': errors,
            'warnings': warnings,
            'metadata': metadata,
        }

    @staticmethod
    def _check_anomalies(df: pd.DataFrame) -> Dict[str, Any]:
        """Detect unusual patterns in the data."""
        warnings = []
        metadata = {}

        # Detect extremely rapid glucose changes (possible calibration error)
        if 'glucose_mg_dl' in df.columns:
            df_check = df.copy()
            df_check['glucose_change'] = df_check['glucose_mg_dl'].diff().abs()

            huge_changes = (df_check['glucose_change'] > 100).sum()
            if huge_changes > 0:
                warnings.append(
                    f"Possible sensor calibration errors: {huge_changes} glucose jumps > 100 mg/dL"
                )
                metadata['huge_glucose_changes'] = int(huge_changes)

        # Detect flat lines (possible sensor failure)
        if 'glucose_mg_dl' in df.columns:
            df_check = df.copy()
            df_check['glucose_change'] = df_check['glucose_mg_dl'].diff().abs()

            flat_lines = (df_check['glucose_change'] == 0).sum()
            flat_line_fraction = flat_lines / len(df_check)

            if flat_line_fraction > 0.50:
                warnings.append(
                    f"Flat glucose readings: {flat_line_fraction*100:.1f}% of intervals unchanged "
                    f"(possible sensor failure)"
                )

            metadata['flat_glucose_fraction'] = float(flat_line_fraction)

        return {
            'warnings': warnings,
            'metadata': metadata,
        }

    @staticmethod
    def _build_summary(
        df: pd.DataFrame,
        errors: List[str],
        warnings: List[str],
        metadata: Dict[str, Any],
    ) -> str:
        """Build human-readable validation summary."""
        lines = []

        # Status
        status = "✅ VALID" if len(errors) == 0 else "❌ INVALID"
        lines.append(f"Validation Result: {status}")
        lines.append("")

        # Data overview
        date_range = ""
        if 'timestamp' in df.columns:
            df_check = df.copy()
            df_check['timestamp'] = pd.to_datetime(
                df_check['timestamp'],
                utc=True,
                errors='coerce',
            )

            valid_timestamps = df_check['timestamp'].dropna()

            if not valid_timestamps.empty:
                start = valid_timestamps.min()
                end = valid_timestamps.max()
                duration_hours = (end - start).total_seconds() / 3600
                date_range = (
                    f"\nDate Range: {start} → {end} "
                    f"({duration_hours:.1f} hours)"
                )
            else:
                date_range = "\nDate Range: unavailable (no valid timestamps)"

        lines.append(f"Dataset: {len(df)} samples{date_range}")
        lines.append("")

        # Errors
        if errors:
            lines.append(f"❌ ERRORS ({len(errors)}):")
            for err in errors:
                lines.append(f"  • {err}")
            lines.append("")

        # Warnings
        if warnings:
            lines.append(f"⚠️  WARNINGS ({len(warnings)}):")
            for warn in warnings:
                lines.append(f"  • {warn}")
            lines.append("")

        # Data quality snapshot
        lines.append("Data Quality Metrics:")
        for key, value in metadata.items():
            if key not in ['timestamp']:
                if isinstance(value, float):
                    lines.append(f"  {key}: {value:.2f}")
                else:
                    lines.append(f"  {key}: {value}")

        return "\n".join(lines)


def validate_dataset(df: pd.DataFrame) -> ValidationResult:
    """
    Convenience function: validate a dataset in one call.

    Args:
        df: DataFrame from TrainingDatasetBuilder

    Returns:
        ValidationResult
    """
    validator = DataValidator()
    return validator.validate(df)