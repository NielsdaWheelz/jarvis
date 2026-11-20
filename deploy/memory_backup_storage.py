"""The private R2 wire format shared by backup and recovery."""

import hashlib
import json
import re
from contextlib import closing, suppress
from pathlib import Path
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

PART_BYTES = 8 * 1024 * 1024
MANIFEST_LIMIT = 1024 * 1024
BUCKET_SETTINGS = {"account", "bucket", "access_key", "secret_key"}
GENERATION = r"[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}"
IMAGE_ID = r"sha256:[0-9a-f]{64}"


def settings(raw, fields):
    config = json.loads(raw)
    if not isinstance(config, dict) or config.keys() != BUCKET_SETTINGS | fields:
        raise ValueError("invalid recovery settings fields")
    if not all(isinstance(v, str) and v and v.isascii() for v in config.values()):
        raise ValueError("invalid recovery settings values")
    if not re.fullmatch("[0-9a-f]{32}", config["account"]) or not re.fullmatch(
        "[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", config["bucket"]
    ):
        raise ValueError("invalid R2 bucket coordinates")
    return config


def producer_settings(raw):
    config = settings(raw, {"recipient", "reader_image", "ping"})
    if (
        not re.fullmatch(r"age1[0-9a-z]{58}", config["recipient"])
        or not re.fullmatch(IMAGE_ID, config["reader_image"])
        or str(UUID(config["ping"])) != config["ping"]
    ):
        raise ValueError("invalid producer settings")
    return config


def measure(path):
    with Path(path).open("rb") as stream:
        size = stream.seek(0, 2)
        stream.seek(0)
        return {
            "bytes": size,
            "sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
        }


class Bucket:
    def __init__(self, config):
        self.name = config["bucket"]
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{config['account']}.r2.cloudflarestorage.com",
            region_name="auto",
            aws_access_key_id=config["access_key"],
            aws_secret_access_key=config["secret_key"],
            config=Config(
                connect_timeout=10,
                read_timeout=30,
                retries={"mode": "standard", "total_max_attempts": 3},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def read(self, key, destination=None, *, limit=None):
        response = self.client.get_object(Bucket=self.name, Key=key)
        digest = hashlib.sha256()
        length = 0
        with closing(response["Body"]) as body:
            for part in body.iter_chunks(chunk_size=PART_BYTES):
                length += len(part)
                if limit is not None and length > limit:
                    raise ValueError("remote object exceeds expected size")
                digest.update(part)
                if destination is not None:
                    destination.write(part)
        if length != response["ContentLength"]:
            raise ValueError("incomplete remote object")
        return {"bytes": length, "sha256": digest.hexdigest()}

    def put_dump(self, key, stream, require_valid_dump):
        target = {"Bucket": self.name, "Key": key}
        upload = self.client.create_multipart_upload(**target)
        request = {**target, "UploadId": upload["UploadId"]}
        digest = hashlib.sha256()
        length = 0
        parts = []
        try:
            while part := stream.read(PART_BYTES):
                length += len(part)
                digest.update(part)
                number = len(parts) + 1
                uploaded = self.client.upload_part(
                    **request, PartNumber=number, Body=part
                )
                parts.append({"PartNumber": number, "ETag": uploaded["ETag"]})
            require_valid_dump()
            expected = {"bytes": length, "sha256": digest.hexdigest()}
            with suppress(BotoCoreError, ClientError):
                # A lost completion response can leave a durable object.
                self.client.complete_multipart_upload(
                    **request, MultipartUpload={"Parts": parts}, IfNoneMatch="*"
                )
            self.verify(key, expected)
            return expected
        finally:
            # Already completed uploads have no remaining parts.
            with suppress(BotoCoreError, ClientError):
                self.client.abort_multipart_upload(**request)

    def put_manifest(self, key, ciphertext):
        if len(ciphertext) > MANIFEST_LIMIT:
            raise ValueError("encrypted manifest exceeds size limit")
        expected = {
            "bytes": len(ciphertext),
            "sha256": hashlib.sha256(ciphertext).hexdigest(),
        }
        with suppress(BotoCoreError, ClientError):
            self.client.put_object(
                Bucket=self.name, Key=key, Body=ciphertext, IfNoneMatch="*"
            )
        self.verify(key, expected)

    def verify(self, key, expected):
        if self.read(key, limit=expected["bytes"]) != expected:
            raise ValueError("remote object differs from published ciphertext")
