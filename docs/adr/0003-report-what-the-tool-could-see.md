# 3. Report what the tool could see, alongside what it found

Date: 2026-08-17

## Status

accepted

## Context

Against three published 2024 labels, the tool reported the same two deviations
every time: no telephone number, and the words "Energy Commission" absent. Both
are listed in section 1393.1(c)(4).

The tool reads a PDF's text layer. A label can also carry content as artwork,
and artwork is invisible to a text extractor. So each of those two findings had
two possible explanations, and the tool could not tell them apart:

1. the element is not on the label, or
2. the element is on the label as a picture.

If the answer was (2), the tool was reporting a limitation of PDF text
extraction as though it were a property of someone else's document, against
named suppliers. That is not a small error. It is the specific way this project
could do harm.

### How it was resolved

Three things, in order of increasing authority.

**The images were enumerated.** Every image the three pages declare is an
indexed-colour raster with a single-entry palette, that is, a one-colour shape.
Their counts, five, seven and ten, are exactly the number of coloured wedges
across each label's pie charts: two for a two-tone pie, one for a single-tone
pie.

**Their placement was measured.** `scripts/inspect_artwork.py` prints the size
at which the page draws each image. The largest on any of the three is 47 by 47
points. All of them sit in one horizontal band, the row headed "Electricity
Sources". Nothing that size holds a legible telephone number.

**The pages were rendered and looked at.** At 150 dpi, all three render as a
table plus one small pie chart per portfolio column. There is no logo, no
wordmark, no contact block, and no telephone number anywhere on any of the
three pages. The words "Energy Commission" do not appear either; the label
names the regulator as "CEC" in the footnote prescribed by section 1393.1(l)(2)
and links energy.ca.gov.

The conclusion is (1). Both deviations are properties of the issued documents,
not artefacts of extraction. Since section 1393.1(i) provides that the Energy
Commission generates the label or supplies the template and the supplier may
not alter the format, what three independent labels agreeing indicates is a
property of the issued template, and it remains a statement about documents
rather than about any supplier.

That settles it for three labels. It does not settle it for the next label
anyone points the tool at.

## Decision

The tool measures how much of a document it was able to see, and says so.

1. `extract.py` counts the images each page declares, following Form XObjects,
   and stores the count on the document.

2. From that count it composes one sentence, the extraction basis, which is
   printed under the document's name on every report and carried in the JSON.
   It says one of four things: this is a plain text file; this PDF embeds N
   images and text inside a picture is not read; this PDF embeds no image, so a
   picture is not the explanation, though vector-drawn text would still not be
   read; or the image resources could not be enumerated, so a picture cannot be
   ruled out.

3. `_bad()` in `checks.py` appends that sentence to every deviation. It is not
   possible to report a deviation from this tool without the basis attached,
   because the constructor that makes a deviation is the thing that attaches
   it.

4. Findings say "does not appear in the extracted text", not "does not appear
   on the label".

5. `scripts/inspect_artwork.py` makes the enumeration and placement reproducible
   for anyone who wants to repeat the resolution above on a document of their
   own. It points the reader at rendering the page, because that is the step
   that actually settles the question.

## Consequences

An absence finding now carries its own qualification, and the qualification is
specific to the document rather than a generic disclaimer. A reader who sees
"embeds no image" is being told something stronger than a reader who sees
"embeds 7 images", and the tool does not pretend otherwise.

The count narrows the question; it does not close it. Inline images are not
counted, and text drawn as vector paths is not an image at all. The zero-image
sentence says so rather than claiming more than was measured.

Reports are longer. The basis repeats on each deviation instead of being stated
once. That is the intended trade: a finding is quoted on its own, and the
sentence has to survive the quoting.

Nothing here is a check, nothing here cites the regulation, and the image count
is not a regulatory quantity. It describes the tool's own reach.
