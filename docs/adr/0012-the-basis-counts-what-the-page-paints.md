# 12. The basis sentence counts what the page paints

Date: 2026-08-22

## Status

accepted

Takes up the residual concession in the extraction basis: that text drawn as
vector paths would not be read. It does not remove the concession. It
measures it.

## Context

ADR 0003 put a count of declared images into every deviation's basis
sentence, so a reader could tell "this document declares nothing a picture
could hide" from "this document embeds seven pictures". One escape hatch was
left open in words rather than in numbers: a page can draw text as filled or
stroked vector outlines - logo lettering, watermark type - and none of it is
declared as an image, so the zero-image sentence narrowed the explanations
without closing them, and said so.

That sentence has been earning its keep. The artwork procedure in
`docs/sources.md` used exactly this reasoning by hand: enumerate what the
page declares, measure where it draws, render only what remains doubtful.
What was never available mechanically was the middle step for artwork that is
neither a raster image nor text: shapes.

A content stream that paints a rectangle or a curve emits a path-painting
operator (`f`, `S`, `B` and kin). Those operators are countable the same way
image declarations are, including inside Form XObjects. The question is not
whether to parse artwork - the tool still reads no drawing - but whether the
sentence attached to every absence should carry a number where it currently
carries a shrug.

The hazard is familiar from ADR 0003: a count that quietly becomes a test.
A page with many painted shapes must never be treated as hiding something,
and a page with none must never be treated as having nothing else to say.

## Decision

Extraction counts path-painting operations alongside images, walks Form
XObjects with the same depth cap and cycle guard, and composes one basis
sentence from both counts:

- No image declared and no shape painted is the strongest position the tool
  can state, and the sentence says so plainly: a picture is not an available
  explanation here.
- Images without shapes, or shapes without images, each say their number.
- Both counts together appear in one sentence, so a reader quoting one
  deviation quotes the whole basis either way.
- Where the shapes cannot be enumerated, the sentence says so rather than
  printing zero, because an enumeration failure printed as zero would be an
  undercount wearing the clothes of certainty - the exact direction ADR 0003
  calls dangerous.

Three fences, matching the ones around the image count:

**One: the count qualifies, it never decides.** No check reads it, no status
turns on it, and `tests/test_geometry.py`'s trick of reading the catalog's
source has a sibling here: nothing under `checks.py` may mention the field.

**Two: no threshold exists anywhere in the code path.** Some other tool
might want to call twenty thousand painted paths "heavy artwork". This one
prints the number and stops. A threshold would convert a description into a
judgment about the document, which is the conversion this project exists to
refuse.

**Three: failure is visible.** An uncountable enumeration produces its own
wording, never a silent zero, mirroring how an uncountable image set already
works.

## Consequences

Every absence finding now states whether artwork of any declared kind could
be hiding the element. On the issued labels read so far, the artwork is pie
chart wedges drawn as small raster images; the shape count is expected to be
small on those documents, which makes the strong sentence available more
often than the old wording admitted. Nothing in the implemented count moves:
this changes what the tool says about what it saw, not what it concludes.

Inline images remain uncounted, as before. The sentence did claim otherwise,
and this is the correction, made on 6 September 2026.

`count_images` enumerates XObjects, an inline image is bytes in the middle of
a content stream, and the zero/zero branch read those two zeros as "no
picture" and printed the strongest sentence the tool has on the one document
class where a picture is exactly the available explanation. `_bad` appends the
basis to every deviation, so each absence finding on such a label carried the
tool's maximally strong claim, wrongly. ADR 0003 had the invariant right --
"the count narrows the question; it does not close it" -- and the wording
adopted here overran it.

The count is still XObjects only, because it is a published field and an
inline image is not declared anywhere. What changed is that the *sentence* no
longer rests on that count alone: `draws_inline_image` walks the same content
streams the paint count already walks, following Form XObjects the same way,
and the tool says a picture is unavailable only where that search came back
empty. Where it finds one, the sentence says so; where the streams could not
be read, it says that instead, because unknown is not zero here either.

What remains outside the sentence, and is named in `docs/AUDITING.md` section
4: text drawn as vector paths is counted as painting rather than read, and
shading patterns are not counted at all.

Type 3 fonts, whose glyphs are themselves little content streams, may
contribute paint operations; they are shapes by this measure and the sentence
describes painting, so the claim stays true even there.
