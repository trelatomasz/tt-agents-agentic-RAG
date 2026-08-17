# Making ingestion idempotent

Ingestion is idempotent when running it twice over unchanged source material leaves the
index byte-identical and costs nothing in embedding calls. It is the property that makes a
scheduled job safe to retry.

## Hash the normalized content, not the file

A file changes whenever its modification time moves, its line endings are rewritten by a
different editor, or trailing whitespace appears. None of those change what a reader sees.
Hashing after normalization means a cosmetic edit produces the same content hash and the
document is skipped, while a real edit produces a new version.

Keep the raw file hash as well. It identifies which bytes were parsed, so a later parser
version can deliberately reprocess the same source without guessing.

## Deletion needs proof

A source adapter that fails to read a file has not discovered that the file is gone. If an
adapter error is treated as a deletion, one permissions problem silently empties a slice of
the index. Deletion therefore requires positive evidence: either the adapter reports the
item as deleted, or a full source snapshot shows the item is absent while every other item
was read successfully.

For this reason `--delete-missing` is never a default. It requires a complete snapshot and
a dry-run summary that a human reads before the tombstones are published.

## Candidate indexes make failure cheap

Writes land in a candidate index run. Evaluation decides. Only then does the active pointer
move, in one step, so a reader sees either the old corpus or the new one. A run that fails
halfway leaves the active index untouched, which turns a partial ingestion from an incident
into a discarded run.

Rollback is the same mechanism in reverse: restore the previous active pointer together
with the source snapshot that produced it. Restoring one without the other produces an
index whose citations point at content that no longer exists.
