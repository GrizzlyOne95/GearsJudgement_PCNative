# vgmstream validation dependency

The audio fixture pipeline uses the official 64-bit Windows CLI build from:

`https://github.com/vgmstream/vgmstream-releases/releases/download/nightly/vgmstream-win64.zip`

The copy acquired on 2026-08-12 identifies itself as:

`vgmstream CLI decoder r2117-182-g672037a0 (Aug 10 2026)`

Hashes for the retained validation copy under `build/tools/vgmstream`:

- archive SHA-256: `77300C7A2A8D088DB3A6072FCA5E49829379116A33B9B570DA53D6A49825E93D`
- `vgmstream-cli.exe` SHA-256: `B63992E9E76E531406A00BA326FF73EDB2BF654D15CEDF80925A2C7C20A0EDFB`

The nightly URL is rolling. Preserve or verify these hashes when reproducing the current evidence.
vgmstream is used only to decode the extracted RIFF/XMA2 fixture to PCM; the project’s separate
source-matched cooker performs PC Ogg encoding.
