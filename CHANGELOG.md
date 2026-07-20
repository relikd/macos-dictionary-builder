# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project does adhere to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.9.3] – 2026-07-20
### Changed
- `readDictTxt` returns an iterator instead of a list
- new intermediate parse step `groupDictKeys` (e.g., filter grouping before write)


## [0.9.2] – 2026-07-14
### Fixed
- Remove additional control characters


## [0.9.1] – 2026-07-14
### Added
- Progress bar for xml parser
- Flag to en-/disable dictionary compression (40% file size but much slower. On a 77mb input file 60min vs. 8min)

### Fixed
- Limit search key to max. 64 characters
- Remove invalid chars from search key
- Remove duplicate search keys by using the same index for both translation directions
- Search by abbreviations will not include original title (reduces duplicate translations)

### Changed
- Rename module `parser` -> `parse`
- Parameter rename `no_reverse` -> `reverse`
- XML parser `Grouping` stores `Pair`s internally (instead of line numbers) (saves a bit of RAM)


## [0.9.0] – 2026-07-04
Initial release


[0.9.3]: https://github.com/relikd/macos-dictionary-builder/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/relikd/macos-dictionary-builder/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/relikd/macos-dictionary-builder/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/relikd/macos-dictionary-builder/tree/v0.9.0
