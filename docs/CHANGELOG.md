# Changelog

## Unreleased

- `NodeCache.snapshot()` has been deprecated in favor of the read-only
  `CacheView` returned by `NodeCache.view()`. Strategy code should avoid
  calling the snapshot helper.
