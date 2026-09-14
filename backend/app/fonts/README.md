# Fonts for Ask's exports

Static cuts of the site's fonts, embedded in PDF exports and used to draw charts.
All are from Google Fonts ([google/fonts](https://github.com/google/fonts)),
under the SIL Open Font License 1.1 (the `OFL-*.txt` files); none declares a
Reserved Font Name, so the cuts keep their names.

| File | From | Cut |
|---|---|---|
| `Fraunces-Medium.ttf` | `ofl/fraunces/Fraunces[SOFT,WONK,opsz,wght].ttf` | wght 500, opsz 24, SOFT 0, WONK 1 (the site's headings) |
| `PublicSans-Regular.ttf`, `-SemiBold.ttf` | `ofl/publicsans/PublicSans[wght].ttf` | wght 400, 600 |
| `PublicSans-Italic.ttf` | `ofl/publicsans/PublicSans-Italic[wght].ttf` | wght 400 |
| `NotoSans-Regular.ttf`, `-SemiBold.ttf` | `ofl/notosans/NotoSans[wdth,wght].ttf` | wght 400, 600, wdth 100; subset to Latin, Latin Extended, IPA (ɛ, ɔ), punctuation and currency (₵) |

Noto Sans is the fallback for characters Public Sans lacks: the cedi sign ₵ and
the Ghanaian letters ɛ, Ɛ, ɔ, Ɔ. The cuts were made with fontTools
(`fontTools.varLib.instancer.instantiateVariableFont`, then `fontTools.subset`
for Noto Sans).
