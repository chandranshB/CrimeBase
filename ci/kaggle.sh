# Kaggle is the state store for the clean data, so a wrong restore followed by a push would overwrite good data with less. Rules here:
#   restore: skip ONLY when the dataset provably doesn't exist yet; any other failure aborts the job.
#   push:    version if it exists, else create; transient errors are retried with back-off.
# The raw documents' state lives in a GitHub release instead (Kaggle unpacks uploaded zips into ~1,600 loose files, and a whole-dataset
# download of that then returns 404); Kaggle only carries a readable copy of them. Needs GH_TOKEN and `permissions: contents: write`.
# Kaggle's newer API tokens (KGAT_...) go in KAGGLE_API_TOKEN; the legacy key goes in KAGGLE_KEY. Accept the new token in either secret.
[ -z "${KAGGLE_API_TOKEN:-}" ] && unset KAGGLE_API_TOKEN
[[ "${KAGGLE_KEY:-}" == KGAT_* ]] && { export KAGGLE_API_TOKEN=$KAGGLE_KEY; unset KAGGLE_KEY; }
RAW_TAG=raw-archive
retry() { for i in 1 2 3 4; do "$@" && return 0; echo "attempt $i failed: $*" >&2; sleep $((i * 30)); done; return 1; }
exists() {
  local out; out=$(retry kaggle datasets list --mine --search "$1" --csv 2>&1) || { echo "cannot list Kaggle datasets" >&2; exit 1; }
  # an auth failure must never be mistaken for "dataset doesn't exist yet"
  grep -qiE "unauthorized|authenticat|credential|KAGGLE_API_TOKEN|forbidden" <<<"$out" && { echo "Kaggle authentication failed: check the KAGGLE_USERNAME / KAGGLE_KEY (or KAGGLE_API_TOKEN) secrets" >&2; exit 1; }
  grep -q "^$KAGGLE_USERNAME/$1," <<<"$out"
}
restore() {  # restore <slug> <dir>
  mkdir -p "$2"
  if exists "$1"; then restore_files "$1" "$2"; else echo "$1 is not on Kaggle yet (first run)"; fi
}
restore_files() {  # restore_files <slug> <dir>: every file, many at a time in one process (ci/kdl.py). The whole-dataset download 404s for hours after a new version, and one CLI call per file takes ~5 s each.
  retry python ci/kdl.py "$KAGGLE_USERNAME/$1" "$2" conflicts.csv || { echo "restore of $1 failed; stopping rather than overwrite it" >&2; exit 1; }  # conflicts.csv: retired 460 MB file
}
restore_raw() {  # restore_raw <dir>: from the release. Without one (first run), only the manifest comes from Kaggle and scrape.py re-fetches the files from the Internet Archive, hash-checked.
  local out; mkdir -p "$1"
  if out=$(gh release view $RAW_TAG 2>&1); then
    retry gh release download $RAW_TAG -D "$1" --clobber || { echo "restore of release $RAW_TAG failed; stopping rather than overwrite it" >&2; exit 1; }
    python ci/bundle.py unpack "$1"
    python ci/bundle.py verify "$1"  # every file the manifest names (bar known-lost ones) must be present, else stop before pushing less than we had
  elif grep -qi "not found" <<<"$out"; then
    if exists crimebase-raw; then retry python ci/kdl.py "$KAGGLE_USERNAME/crimebase-raw" "$1" +manifest.csv +live_state.json || { echo "cannot read the manifest from Kaggle" >&2; exit 1; }
    else echo "no raw archive yet (first run)"; fi
  else echo "cannot query releases: $out" >&2; exit 1; fi
}
push_raw() {  # push_raw <dir> <message>: the release is the state; the Kaggle copy follows
  python ci/bundle.py pack "$1" data/_raw_push
  # bundles before manifest: a half-finished upload leaves an old manifest over a superset of files, which is still consistent
  local files=(data/_raw_push/raw-*.zip data/_raw_push/manifest.csv data/_raw_push/live_state.json); [ -f data/_raw_push/lost.json ] && files+=(data/_raw_push/lost.json)
  if gh release view $RAW_TAG >/dev/null 2>&1; then retry gh release upload $RAW_TAG "${files[@]}" --clobber
  else retry gh release create $RAW_TAG "${files[@]}" --latest=false --title "Raw document archive" --notes "Original documents behind CrimeBase (raw-0..f.zip, named by the first hex digit of each file; manifest.csv lists source URL, Wayback permalink and hash). Rewritten by the archive workflow; the same files are on Kaggle as crimebase-raw."; fi
  [ -f data/clean/documents.csv ] && cp data/clean/documents.csv data/_raw_push/  # the catalogue travels with the files it describes
  push crimebase-raw data/_raw_push kaggle/raw.json "$2"
}
notebook() {  # notebook <dataset slug>: publish the quick-start notebook; it is public only once its dataset is
  local cur; cur=$(mktemp -d)
  { kaggle datasets metadata "$KAGGLE_USERNAME/$1" -p "$cur" > /dev/null && python ci/kmeta.py kernel kaggle/notebook "$KAGGLE_USERNAME" "$cur/dataset-metadata.json" && retry kaggle kernels push -p kaggle/notebook; }     || echo "::warning::could not publish the quick-start notebook"
}
push() {  # push <slug> <dir> <metadata template> <message>
  python ci/kmeta.py prep "$3" "$2" "$KAGGLE_USERNAME"
  if exists "$1"; then retry kaggle datasets version -p "$2" -m "$4"; else retry kaggle datasets create -p "$2"; fi
}
polish() {  # polish <slug> <dir>: settings `datasets version` ignores (column docs, sources, update frequency, cover image). Privacy is read back from Kaggle, never changed.
  local ref="$KAGGLE_USERNAME/$1" cur; cur=$(mktemp -d)
  for _ in $(seq 20); do [[ "$(kaggle datasets status "$ref" 2>/dev/null)" == *ready* ]] && break; sleep 30; done
  { kaggle datasets metadata "$ref" -p "$cur" > /dev/null && python ci/kmeta.py apply "$2/dataset-metadata.json" "$cur/dataset-metadata.json" && retry kaggle datasets metadata "$ref" -p "$2" --update; } \
    || echo "::warning::could not update the listing settings of $ref (data was pushed)"
}
