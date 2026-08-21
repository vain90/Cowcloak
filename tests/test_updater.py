from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATER = (ROOT / "update.sh").read_text(encoding="utf-8")


def test_self_update_does_not_create_script_backup():
    assert 'backup_file="${SCRIPT_PATH}.previous"' not in UPDATER
    assert 'cp -a "${SCRIPT_PATH}"' not in UPDATER
    assert 'rm -f "${SCRIPT_PATH}.previous"' in UPDATER


def test_container_image_rollback_is_still_kept():
    assert 'docker tag "${CURRENT_IMAGE_ID}" "${IMAGE}:previous"' in UPDATER
