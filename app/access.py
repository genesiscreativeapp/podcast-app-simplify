"""Qui voit quoi, qui modifie quoi.

- L'administrateur a tous les droits.
- Un utilisateur voit ses propres dossiers et ceux qui lui sont attribués (sous-dossiers compris).
- Il ne modifie, déplace ou supprime que ce qu'il a créé lui-même : un dossier créé par l'administration
  (ou par un autre) reste en lecture / travail, jamais en modification.
"""
from fastapi import HTTPException

from .db import Folder, FolderAccess, Job, User

NOT_YOURS_FOLDER = "Ce dossier a été créé par l'administration : vous pouvez y travailler, pas le modifier ni le supprimer."
NOT_YOURS_JOB = "Ce podcast n'a pas été créé par vous : vous ne pouvez pas le modifier ni le supprimer."


class Access:
    def __init__(self, s, user: User):
        self.user, self.admin = user, user.is_admin
        self.folders = {f.id: f for f in s.query(Folder).filter(Folder.deleted_at.is_(None))}  # la corbeille n'apparaît nulle part ailleurs
        self.assigned = {r[0] for r in s.query(FolderAccess.folder_id).filter(FolderAccess.user_id == user.id)}
        self._visible: set[int] | None = None

    def _chain(self, fid):  # le dossier puis ses parents
        seen = set()
        while fid and fid in self.folders and fid not in seen:
            seen.add(fid)
            yield self.folders[fid]
            fid = self.folders[fid].parent_id

    def can_see(self, fid) -> bool:
        return self.admin or fid in self.visible_ids()

    def visible_ids(self) -> set[int]:
        """Ids des dossiers visibles (admin : tous). Mis en cache pour la requête."""
        if self._visible is None:
            self._visible = set(self.folders) if self.admin else {
                fid for fid in self.folders
                if any(f.id in self.assigned or f.created_by == self.user.username for f in self._chain(fid))}
        return self._visible

    def owns_folder(self, fid) -> bool:
        f = self.folders.get(fid)
        return bool(f) and (self.admin or f.created_by == self.user.username)

    def owns_job(self, job: Job) -> bool:
        return self.admin or job.created_by == self.user.username

    def jobs(self, query):
        """Restreint une requête sur Job aux traitements hors corbeille des dossiers visibles."""
        query = query.filter(Job.deleted_at.is_(None))
        return query if self.admin else query.filter(Job.folder_id.in_(self.visible_ids() or {-1}))

    def need_folder(self, fid) -> Folder:
        if not self.can_see(fid) or fid not in self.folders:
            raise HTTPException(404, "Dossier introuvable")
        return self.folders[fid]

    def need_folder_edit(self, fid) -> Folder:
        f = self.need_folder(fid)
        if not self.owns_folder(fid):
            raise HTTPException(403, NOT_YOURS_FOLDER)
        return f

    def need_job(self, s, job_id, edit=False) -> Job:
        job = s.get(Job, job_id)
        if job is None or job.deleted_at is not None or not self.can_see(job.folder_id):
            raise HTTPException(404, "Traitement introuvable")
        if edit and not self.owns_job(job):
            raise HTTPException(403, NOT_YOURS_JOB)
        return job
