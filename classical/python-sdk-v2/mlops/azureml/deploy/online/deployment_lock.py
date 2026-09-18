from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator

LEASE_DURATION_SECONDS = 60
LEASE_RENEWAL_SECONDS = 20


class RenewableLease:
    def __init__(self, lease_client: Any) -> None:
        self._lease_client = lease_client
        self._stop = threading.Event()
        self._renewal_error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._renew,
            name="online-endpoint-deployment-lock",
            daemon=True,
        )

    def acquire(self) -> None:
        self._lease_client.acquire(lease_duration=LEASE_DURATION_SECONDS)
        self._thread.start()

    def _renew(self) -> None:
        while not self._stop.wait(LEASE_RENEWAL_SECONDS):
            try:
                self._lease_client.renew()
            except Exception as error:
                self._renewal_error = error
                self._stop.set()

    def ensure_held(self) -> None:
        if self._renewal_error is not None:
            raise RuntimeError(
                "Lost the Azure deployment lock lease; refusing to continue."
            ) from self._renewal_error

    def release(self) -> None:
        self._stop.set()
        self._thread.join(timeout=LEASE_RENEWAL_SECONDS)
        release_error = None
        try:
            self._lease_client.release()
        except Exception as error:
            release_error = error
        if self._renewal_error is not None:
            raise RuntimeError(
                "Lost the Azure deployment lock lease; refusing to continue."
            ) from self._renewal_error
        if release_error is not None:
            raise release_error


@contextmanager
def endpoint_deployment_lock(
    credential: Any,
    storage_account_name: str,
    container_name: str,
    endpoint_name: str,
) -> Iterator[RenewableLease]:
    from azure.core.exceptions import HttpResponseError, ResourceExistsError
    from azure.storage.blob import BlobClient, BlobLeaseClient

    blob_client = BlobClient(
        account_url=f"https://{storage_account_name}.blob.core.windows.net",
        container_name=container_name,
        blob_name=f"{endpoint_name}.lock",
        credential=credential,
    )
    try:
        blob_client.upload_blob(b"", overwrite=False)
    except ResourceExistsError:
        pass

    lease = RenewableLease(BlobLeaseClient(blob_client))
    try:
        lease.acquire()
    except HttpResponseError as error:
        if error.status_code == 409:
            raise RuntimeError(
                f"Another deployment holds the Azure lease for endpoint "
                f"{endpoint_name!r}. Wait for it to finish or for the "
                f"{LEASE_DURATION_SECONDS}-second stale lease to expire."
            ) from error
        raise

    try:
        yield lease
    except BaseException as error:
        try:
            lease.release()
        except BaseException as release_error:
            error.add_note(f"Failed to release deployment lock: {release_error}")
        raise
    else:
        lease.release()
