import re
from collections import defaultdict
from datetime import date

from backend.app.models.analytics import AnalyticsResponse, MetricTrend, RiskSignal, TrendPoint
from backend.app.services.records import RecordStore


class ClinicalAnalyticsService:
    """Compute transparent trends and review signals from stored observations."""

    def __init__(self, records: RecordStore) -> None:
        self.records = records

    def analyze(self, owner_id: str | None = None) -> AnalyticsResponse:
        points_by_metric: dict[str, list[TrendPoint]] = defaultdict(list)
        signals: list[RiskSignal] = []
        summaries = self.records.list_records(owner_id) if owner_id is not None else self.records.list_records()
        for summary in summaries:
            detail = self.records.get_record(summary.id, owner_id) if owner_id is not None else self.records.get_record(summary.id)
            if not detail or not detail.structured:
                continue
            document_date = detail.structured.document_date
            for observation in detail.structured.observations:
                for metric, value, unit in self._numeric_values(observation.name, observation.value, observation.unit):
                    observed_on = observation.observed_on or document_date
                    point = TrendPoint(
                        observed_on=observed_on,
                        value=value,
                        unit=unit,
                        record_id=summary.id,
                        citation_id=f"{summary.id}#structured",
                    )
                    points_by_metric[metric].append(point)
                    signal = self._threshold_signal(metric, point)
                    if signal:
                        signals.append(signal)

        trends = [self._trend(metric, points) for metric, points in points_by_metric.items()]
        trends.sort(key=lambda item: item.metric)
        return AnalyticsResponse(trends=trends, signals=signals)

    @staticmethod
    def _numeric_values(name: str, value: str, unit: str | None):
        if name == "blood_pressure":
            match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*", value)
            if not match:
                return []
            return [("blood_pressure_systolic", float(match.group(1)), unit), ("blood_pressure_diastolic", float(match.group(2)), unit)]
        try:
            return [(name, float(value), unit)]
        except ValueError:
            return []

    @staticmethod
    def _trend(metric: str, points: list[TrendPoint]) -> MetricTrend:
        ordered = sorted(points, key=lambda point: point.observed_on or date.min)
        if len(ordered) < 2:
            return MetricTrend(metric=metric, direction="insufficient_data", points=ordered, latest_value=ordered[-1].value if ordered else None)
        change = ordered[-1].value - ordered[0].value
        baseline = abs(ordered[0].value) or 1
        relative_change = abs(change) / baseline
        direction = "stable" if relative_change < 0.05 else ("increasing" if change > 0 else "decreasing")
        return MetricTrend(metric=metric, direction=direction, points=ordered, latest_value=ordered[-1].value, change=round(change, 4))

    @staticmethod
    def _threshold_signal(metric: str, point: TrendPoint) -> RiskSignal | None:
        if metric not in {"blood_pressure_systolic", "blood_pressure_diastolic"}:
            return None
        threshold = 180 if metric.endswith("systolic") else 120
        if point.value <= threshold:
            return None
        reference = "https://www.heart.org/en/health-topics/high-blood-pressure/"
        return RiskSignal(
            code="possible_severe_blood_pressure",
            severity="urgent_review",
            metric=metric,
            title="Blood-pressure reading needs prompt review",
            detail=(
                f"The recorded {metric.replace('_', ' ')} value was {point.value:g}, above the {threshold} reference threshold. "
                "Verify the measurement and seek professional medical guidance; if urgent symptoms are present, contact local emergency services."
            ),
            observed_on=point.observed_on,
            record_id=point.record_id,
            citation_id=point.citation_id,
            source_reference=reference,
        )
