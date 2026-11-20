"""Operator-side staging and reporting for a network-isolated memory restore."""

import fcntl
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from memory_backup_storage import (
    GENERATION,
    IMAGE_ID,
    MANIFEST_LIMIT,
    Bucket,
    measure,
    settings,
)

from jarvis._atomic_json import read_private_json, replace_private_json

DEADLINE_SECONDS = 7200


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encrypted_directory(path):
    device = (
        subprocess.check_output(["df", "-P", path], text=True)
        .splitlines()[1]
        .split(maxsplit=1)[0]
    )
    return (
        plistlib.loads(
            subprocess.check_output(["diskutil", "info", "-plist", device])
        ).get("FileVault")
        is True
    )


def private(path, mode):
    info = path.lstat()
    return (
        stat.S_IMODE(info.st_mode) == mode
        and info.st_uid == os.getuid()
        and not stat.S_ISLNK(info.st_mode)
    )


def decrypt(kit, source, target):
    with target.open("xb") as output:
        subprocess.run(
            ["age", "--decrypt", "--identity", kit / "identity", source],
            stdout=output,
            stderr=subprocess.DEVNULL,
            check=True,
        )


def download(config, generation, name, target, limit):
    with target.open("xb") as output:
        return config.read(f"{generation}/{name}", output, limit=limit)


def load_reader(archive, image):
    runtime = json.loads(subprocess.check_output(["docker", "context", "inspect"]))[0][
        "Endpoints"
    ]["docker"]["Host"]
    require(
        runtime.startswith("unix://")
        and not os.environ.get("DOCKER_CONTEXT")
        and not os.environ.get("DOCKER_HOST"),
        "select a local docker engine through its native context",
    )
    with tarfile.open(archive) as bundle:
        (descriptor,) = json.load(bundle.extractfile("index.json"))["manifests"]
        require(descriptor["digest"] == image, "archive names a different reader")
        with bundle.extractfile(
            f"blobs/sha256/{image.removeprefix('sha256:')}"
        ) as index:
            packed = hashlib.file_digest(index, "sha256").hexdigest()
    require(image == f"sha256:{packed}", "archive does not contain the pinned index")
    subprocess.run(
        ["docker", "image", "load", "--input", archive],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    require(
        subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        == image,
        "reader image identity differs from the manifest",
    )


def isolated_read(stage, image, remaining):
    name = f"jarvis-memory-restore-{uuid4().hex}"
    work = stage / "work"
    work.mkdir(mode=0o700)
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--pull",
                "never",
                "--name",
                name,
                "--network",
                "none",
                "--mount",
                f"type=bind,src={stage},dst=/input,readonly",
                "--mount",
                f"type=bind,src={work},dst=/work",
                image,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=remaining,
        )
        return json.loads(result.stdout), result.returncode
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )


def retain(kit, generation, stage, image_archive):
    directory = kit / "held"
    directory.mkdir(mode=0o700, exist_ok=True)
    require(private(directory, 0o700), "held storage must be owner-private")
    selected = directory / "current.json"
    receipt = read_private_json(selected)
    if receipt is not None:
        previous = receipt["generation"]
        require(re.fullmatch(GENERATION, previous), "invalid held generation")
        if generation.split("-")[0] <= previous.split("-")[0]:
            return previous
    with tempfile.TemporaryDirectory(dir=directory) as scratch:
        staged = Path(scratch)
        for source, name in (
            (stage / "database.age", "database.age"),
            (stage / "manifest.age", "manifest.age"),
            (image_archive, "reader.tar"),
        ):
            target = staged / name
            shutil.copyfile(source, target)
            with target.open("rb") as stream:
                os.fsync(stream.fileno())
            require(
                measure(source) == measure(target), "held ciphertext or image mismatch"
            )
        files = {file.name: measure(file) for file in staged.iterdir()}
        candidate = directory / generation
        if candidate.is_dir():
            # A previous interrupted promotion can leave an unselected directory.
            shutil.rmtree(candidate)
        os.rename(staged, candidate)
        replace_private_json(selected, {"generation": generation, "files": files})
    if receipt is not None:
        shutil.rmtree(directory / previous)
    return generation


def restore(location, generation, destination, started_utc, started):
    require(sys.platform == "darwin", "run the restore from the mac")
    require(
        location in {"r2", "held"} and re.fullmatch(GENERATION, generation),
        "select an exact r2 or held generation",
    )
    kit = Path(os.environ["JARVIS_RECOVERY_KIT"]).resolve(strict=True)
    require(
        private(kit, 0o700) and private(kit / "identity", 0o600),
        "owner kit and age identity must be private",
    )
    require(kit.is_dir() and (kit / "identity").is_file(), "invalid owner kit")
    require(
        encrypted_directory(kit) and encrypted_directory(destination.parent),
        "owner kit and restore directory must be on filevault volumes",
    )
    destination.mkdir(mode=0o700)
    report = {"generation": generation, "location": location}
    phase = "stage selected generation"
    try:
        with (kit / ".held-lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with tempfile.TemporaryDirectory(dir=destination) as scratch:
                stage = Path(scratch)
                if location == "r2":
                    config = kit / "restore.json"
                    require(
                        private(config, 0o600), "R2 restore settings must be private"
                    )
                    bucket = Bucket(settings(config.read_bytes(), set()))
                    download(
                        bucket,
                        generation,
                        "manifest.age",
                        stage / "manifest.age",
                        MANIFEST_LIMIT,
                    )
                else:
                    held = kit / "held"
                    receipt = read_private_json(held / "current.json")
                    require(
                        receipt and receipt["generation"] == generation,
                        "requested generation is not the held copy",
                    )
                    for file in ("manifest.age", "database.age", "reader.tar"):
                        require(
                            measure(held / generation / file) == receipt["files"][file],
                            f"held {file} differs from its verified copy",
                        )
                    shutil.copyfile(
                        held / generation / "manifest.age", stage / "manifest.age"
                    )

                phase = "decrypt and validate manifest"
                manifest_path = stage / "manifest.json"
                decrypt(kit, stage / "manifest.age", manifest_path)
                manifest = json.loads(manifest_path.read_bytes())
                image = manifest["reader_image"]
                cut = datetime.fromisoformat(manifest["cut_utc"])
                require(
                    manifest["version"] == 1
                    and manifest["generation"] == generation
                    and cut.utcoffset() == timedelta(0)
                    and generation.startswith(cut.strftime("%Y%m%dT%H%M%S%fZ") + "-")
                    and re.fullmatch(IMAGE_ID, image),
                    "manifest version, generation, cut or reader identity differs",
                )
                expected = manifest["ciphertext"]
                require(
                    isinstance(expected["bytes"], int)
                    and expected["bytes"] > 0
                    and re.fullmatch(r"[0-9a-f]{64}", expected["sha256"]),
                    "invalid ciphertext inventory",
                )
                age = (started_utc - cut).total_seconds()
                require(age >= 0, "selected backup cut is in the future")
                report.update(
                    cut_utc=manifest["cut_utc"],
                    cut_age_seconds=round(age),
                    within_24_hours=age <= 86400,
                )
                phase = "fetch and verify dump ciphertext"
                if location == "r2":
                    observed = download(
                        bucket,
                        generation,
                        "database.age",
                        stage / "database.age",
                        expected["bytes"],
                    )
                    archive = kit / "readers" / f"{image.removeprefix('sha256:')}.tar"
                else:
                    shutil.copyfile(
                        held / generation / "database.age", stage / "database.age"
                    )
                    observed = measure(stage / "database.age")
                    archive = held / generation / "reader.tar"
                require(
                    observed == expected, "dump ciphertext differs from the manifest"
                )
                phase = "decrypt dump and load pinned reader"
                decrypt(kit, stage / "database.age", stage / "database.dump")
                load_reader(archive, image)
                phase = "restore and verify isolated memory reads"
                remaining = DEADLINE_SECONDS - (time.monotonic() - started)
                require(
                    remaining > 0, "restore missed the two-hour deadline before reading"
                )
                reader_report, exit_code = isolated_read(stage, image, remaining)
                elapsed = time.monotonic() - started
                report.update(reader=reader_report, seconds_to_read=round(elapsed, 3))
                require(
                    exit_code == 0, "isolated database or witness comparison failed"
                )
                require(
                    elapsed <= DEADLINE_SECONDS,
                    "verified reads missed the two-hour deadline",
                )
                if location == "r2":
                    phase = "verify and select held recovery copy"
                    report["held_generation"] = retain(kit, generation, stage, archive)
        report["result"] = "verified"
    except Exception as error:
        report.update(
            result="failed",
            failed_phase=phase,
            error=str(error) if type(error) is ValueError else type(error).__name__,
            elapsed_seconds=round(time.monotonic() - started, 3),
        )
    replace_private_json(destination / "restore-report.json", report)
    print(f"{report['result']}. private report: {destination / 'restore-report.json'}")
    return 0 if report["result"] == "verified" else 1


if __name__ == "__main__":
    started = time.monotonic()
    started_utc = datetime.now(UTC)
    os.umask(0o077)
    try:
        if len(sys.argv) != 3 or "/" not in sys.argv[1]:
            raise ValueError(
                "usage: deploy/memory-restore {r2|held}/GENERATION NEW_PRIVATE_DIR"
            )
        location, generation = sys.argv[1].split("/", 1)
        sys.exit(
            restore(
                location, generation, Path(sys.argv[2]).absolute(), started_utc, started
            )
        )
    except (KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(
            str(error) if type(error) is ValueError else type(error).__name__,
            file=sys.stderr,
        )
        sys.exit(1)
