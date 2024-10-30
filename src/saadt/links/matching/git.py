import git as gitpy


class Repo:
    _files: list[str] | None
    _path: str
    _url: str

    clone_opts: list[str]
    repo: gitpy.Repo

    def __init__(self, url: str, path: str, clone_opts: list[str] | None = None, exists: bool = False):
        self._files = None
        self._path = path
        self._url = url
        self.clone_opts = clone_opts or ["--filter=tree:0", "--depth=1", "--sparse"]

        if not exists:
            self.repo = gitpy.Repo.clone_from(url=self._url, to_path=self._path, multi_options=self.clone_opts)
        else:
            self.repo = gitpy.Repo(path)

    @property
    def path(self) -> str:
        return self._path

    @property
    def url(self) -> str:
        return self._url

    def files(self) -> list[str]:
        if self._files is None:
            self._files = self.repo.git.ls_files().splitlines()
        assert self._files is not None
        return self._files

    def readfile(self, path: str) -> str:
        return self.repo.git.show(f"{self.repo.head.commit.hexsha}:{path}")  # type: ignore[no-any-return]
