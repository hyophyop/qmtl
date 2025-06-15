# Changelog

## Unreleased

- `NodeCache.snapshot()` has been deprecated in favor of the read-only
  `CacheView` returned by `NodeCache.view()`. Strategy code should avoid
  calling the snapshot helper.
- Added `coverage()` and `fill_missing()` interfaces for history providers and
  removed `start`/`end` arguments from `StreamInput`.
