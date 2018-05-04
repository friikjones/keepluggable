"""A simple local filesystem storage backend."""

from pathlib import Path
from shutil import rmtree
from typing import Any, Dict, Sequence
from bag.settings import resolve_path

from keepluggable.orchestrator import get_middle_path, Orchestrator
from keepluggable.storage_file import BasePayloadStorage

MEGABYTE = 1048576


class LocalFilesystemStorage(BasePayloadStorage):
    """Local filesystem storage backend.

    You should use this for testing only because it is not very robust.
    It stores files in a very simple directory scheme::

        base_storage_directory / namespace / key

    Performance will suffer as soon as a couple of thousand files are
    stored in a namespace.

    Keys are MD5 hashes by default. To change this, you would modify
    the action, not the storage backend.

    To enable this backend, use this configuration::

        storage.file = keepluggable.storage_file.local:LocalFilesystemStorage

    **Configuration settings**

    Specify in which directory to store payloads like this::

        local.storage_path = some.python.resource:relative/directory
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        """Construct with an Orchestrator instance."""
        super(LocalFilesystemStorage, self).__init__(orchestrator)
        self.storage_path = orchestrator.settings.read('local.storage_path')
        self.directory = resolve_path(self.storage_path).absolute()
        if not self.directory.exists():
            self.directory.mkdir(parents=True)

    def _dir_of(self, namespace: str) -> Path:
        """Figure out the directory where we store the given ``namespace``."""
        return self.directory / get_middle_path(
            name=self.orchestrator.name, namespace=namespace)

    def get_reader(self, namespace, metadata):
        """Return a stream for the file content."""
        try:
            return open(str(
                self.directory / str(namespace) / self._get_filename(
                    metadata)), 'rb')
        except FileNotFoundError as e:
            raise KeyError(
                'Key not found: {} / {}'.format(
                    namespace, metadata['md5'])) from e

    def put(self, namespace, metadata, bytes_io):
        """Store a file (``bytes_io``) inside ``namespace``."""
        if bytes_io.tell():
            bytes_io.seek(0)
        outdir = self._dir_of(namespace)
        if not outdir.exists():
            outdir.mkdir(parents=True)  # Create namespace directory as needed
        outfile = outdir / self._get_filename(metadata)
        with open(str(outfile), mode='wb', buffering=MEGABYTE) as writer:
            while True:
                chunk = bytes_io.read(MEGABYTE)
                if chunk:
                    writer.write(chunk)
                else:
                    break
        assert outfile.lstat().st_size == metadata['length']

    def get_url(
        self, namespace: str, metadata: Dict[str, Any], seconds: int = 3600,
        https: bool = True,
    ) -> str:
        """Return a Pyramid static URL.

        If you use another web framework, please override this method.

        The ``seconds`` and ``https`` params are ignored.
        """
        from pyramid.threadlocal import get_current_request  # TODO bad way
        request = get_current_request()
        if request is None:  # In a shell command, for instance,
            return ''        # the URL is not important.
        return request.static_path('/'.join((
            self.storage_path,
            get_middle_path(name=self.orchestrator.name, namespace=namespace),
            self._get_filename(metadata))))

    def delete(
        self, namespace: str, metadatas: Sequence[Dict[str, Any]],
    ) -> None:
        """Delete many files."""
        base_path = self._dir_of(namespace)
        for metadata in metadatas:
            path = base_path / self._get_filename(metadata)
            if path.exists():
                path.unlink()

    def get_superpowers(self):
        """Get a really dangerous subclass instance."""
        return LocalFilesystemPower(self.orchestrator)


class LocalFilesystemPower(LocalFilesystemStorage):
    """A subclass that contains dangerous methods."""

    def gen_paths(self, namespace, bucket=None):
        """Generate the paths in a namespace. Too costly -- avoid."""
        the_dir = self._dir_of(namespace)
        for f in the_dir.iterdir():
            yield f  # TODO TEST OR DELETE METHOD

    def delete_namespace(self, namespace):
        """Delete all files in ``namespace``."""
        rmtree(self._dir_of(namespace))

    def empty_bucket(self, bucket=None):
        """Empty the whole bucket, deleting namespaces and files."""
        for sub in self.directory.iterdir():
            rmtree(sub)
