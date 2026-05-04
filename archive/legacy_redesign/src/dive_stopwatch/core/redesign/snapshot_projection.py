from __future__ import annotations

from dataclasses import dataclass

from ..air_o2_snapshot import Snapshot


@dataclass
class SnapshotProjection:
    mode_text: str
    status_text: str = ""
    status_value_text: str = ""
    depth_text: str = ""
    primary_text: str = "00:00.0"
    profile_schedule_text: str = ""
    status_value_kind: str = "default"
    primary_value_text: str | None = None
    primary_value_kind: str = "default"
    depth_timer_text: str = ""
    depth_timer_kind: str = "default"
    remaining_text: str = ""
    summary_text: str = ""
    summary_value_kind: str = "default"
    detail_text: str = ""
    primary_button_label: str = ""
    secondary_button_label: str = ""
    primary_button_enabled: bool | None = None
    secondary_button_enabled: bool | None = None

    def to_snapshot(self) -> Snapshot:
        primary_value_text = self.primary_text if self.primary_value_text is None else self.primary_value_text
        primary_button_enabled = bool(self.primary_button_label) if self.primary_button_enabled is None else self.primary_button_enabled
        secondary_button_enabled = bool(self.secondary_button_label) if self.secondary_button_enabled is None else self.secondary_button_enabled
        return Snapshot(
            mode_text=self.mode_text,
            profile_schedule_text=self.profile_schedule_text,
            status_text=self.status_text,
            status_value_text=self.status_value_text,
            status_value_kind=self.status_value_kind,
            primary_text=self.primary_text,
            primary_value_text=primary_value_text,
            primary_value_kind=self.primary_value_kind,
            depth_text=self.depth_text,
            depth_timer_text=self.depth_timer_text,
            depth_timer_kind=self.depth_timer_kind,
            remaining_text=self.remaining_text,
            summary_text=self.summary_text,
            summary_value_kind=self.summary_value_kind,
            detail_text=self.detail_text,
            primary_button_label=self.primary_button_label,
            secondary_button_label=self.secondary_button_label,
            primary_button_enabled=primary_button_enabled,
            secondary_button_enabled=secondary_button_enabled,
        )

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot) -> SnapshotProjection:
        return cls(
            mode_text=snapshot.mode_text,
            profile_schedule_text=snapshot.profile_schedule_text,
            status_text=snapshot.status_text,
            status_value_text=snapshot.status_value_text,
            status_value_kind=snapshot.status_value_kind,
            primary_text=snapshot.primary_text,
            primary_value_text=snapshot.primary_value_text,
            primary_value_kind=snapshot.primary_value_kind,
            depth_text=snapshot.depth_text,
            depth_timer_text=snapshot.depth_timer_text,
            depth_timer_kind=snapshot.depth_timer_kind,
            remaining_text=snapshot.remaining_text,
            summary_text=snapshot.summary_text,
            summary_value_kind=snapshot.summary_value_kind,
            detail_text=snapshot.detail_text,
            primary_button_label=snapshot.primary_button_label,
            secondary_button_label=snapshot.secondary_button_label,
            primary_button_enabled=snapshot.primary_button_enabled,
            secondary_button_enabled=snapshot.secondary_button_enabled,
        )


def build_snapshot(**kwargs: object) -> Snapshot:
    return SnapshotProjection(**kwargs).to_snapshot()


def replace_snapshot(snapshot: Snapshot, **changes: object) -> Snapshot:
    projection = SnapshotProjection.from_snapshot(snapshot)
    for key, value in changes.items():
        setattr(projection, key, value)
    return projection.to_snapshot()
