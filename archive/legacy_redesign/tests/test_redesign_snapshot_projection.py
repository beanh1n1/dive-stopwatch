from dive_stopwatch.core.redesign.snapshot_projection import SnapshotProjection, replace_snapshot


def test_snapshot_projection_applies_transitional_defaults() -> None:
    snapshot = SnapshotProjection(
        mode_text="AIR/O2",
        status_text="AT O2 STOP",
        status_value_text="On O2",
        primary_text="12:34.5",
        depth_text="30 fsw",
        primary_button_label="Leave Stop",
    ).to_snapshot()

    assert snapshot.primary_value_text == "12:34.5"
    assert snapshot.primary_button_enabled is True
    assert snapshot.secondary_button_enabled is False


def test_replace_snapshot_round_trips_existing_fields() -> None:
    original = SnapshotProjection(
        mode_text="SURD",
        status_text="READY",
        status_value_text="Ready",
        depth_text="50 fsw",
        summary_text="Next: Chamber 50",
    ).to_snapshot()

    updated = replace_snapshot(original, summary_text="Next: On O2", summary_value_kind="o2")

    assert updated.mode_text == "SURD"
    assert updated.status_text == "READY"
    assert updated.depth_text == "50 fsw"
    assert updated.summary_text == "Next: On O2"
    assert updated.summary_value_kind == "o2"
