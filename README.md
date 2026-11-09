# S2action

GitHub Actions workflow for building S2Arm game resource packs on a macOS runner.

This repository contains CI orchestration only. It does not include S2Arm source code, game dumps, Nintendo keys, or generated game resources.

## Security

The repository is public. Never commit game files, `prod.keys`, signed download URLs, or generated resource packs. Configure input URLs and keys as GitHub Actions secrets. Do not enable public artifact upload unless you explicitly accept that repository visitors may be able to download the generated artifact.

The workflow implementation is being added on a separate test branch first.
