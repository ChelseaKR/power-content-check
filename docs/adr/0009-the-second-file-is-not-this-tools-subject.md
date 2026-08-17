# 9. The second file published beside a label is not this tool's subject

Date: 2026-08-17

## Status

accepted

## Context

The Energy Commission publishes two files for each retail supplier on the same
index page: a PDF, and a spreadsheet its own link text calls "Excel". Ninety of
the ninety one entries carry both.

Reading the spreadsheets raised a real question about this tool. PCL004 reports,
on every published label read, that the words "Energy Commission" do not appear.
ADR 0003 settled that this is a property of the PDF rather than an artefact of
extraction: the pages were enumerated, measured and rendered, and the PDF names
the regulator as "CEC" and links energy.ca.gov and nowhere writes the name out.
Every workbook read does write it out, as "California Energy Commission - Power
Source Disclosure".

So if "the label" means both files, PCL004's deviation is not a deviation at
all, and this tool has been reporting an absence from one rendering of a
disclosure that the other rendering does not have. That is worth deciding
explicitly rather than by continuing to read only what the tool already reads.

There are three answers available.

**A. Leave the tool as it is.** It reads PDF and plain text. The workbook is
recorded in `docs/sources.md` and nowhere else.

**B. Read the workbook as its own document.** Each file checked separately, no
merging, a new extraction basis sentence for a spreadsheet the way there is one
for a PDF.

**C. Treat the pair as one label.** Union the text of both files and check the
union. This is the answer that makes PCL004's deviation disappear.

### What the workbook says about itself

Each one carries a sentence, in a cell, that the Energy Commission wrote:

> This is an alternative version of the 2024 power content label for [supplier].
> It provides the greenhouse gas intensity and fuel source mix for each
> electricity portfolio offered to consumers by [supplier], as well as the
> quantity of unbundled renewable energy credits associated with each portfolio.
> This file also includes statewide numbers for comparison.

Its single sheet is named "PCL Alternative Version". It says it provides three
of the things the label discloses. It does not say it is the label, and it does
not carry the label's structure: there is no "Renewables and Zero-Carbon
Resources" group and no "Fossil Fuels" group, both of which section 1393.1(c)(2)
requires, and unspecified power is a row with no annotation, which section
1393.1(c)(7) requires.

### What checking one would produce

The four workbooks were read out to text and the catalog run over them, outside
this tool, to find out. Each produced seven deviations rather than two: no
telephone number, no supplier web address, no Energy Commission web address, one
of the ten fuel type categories missing because the workbook writes "RPS
Eligible Hydroelectric" where the regulation writes "Eligible hydroelectric",
neither resource group, and no unspecified power annotation. PCL004 conforms,
and so does the statewide disclosure and the data year.

Two of those seven are the tool's fault rather than the document's, in exactly
the shape ADR 0006 catalogued. The workbook's two web addresses are hyperlinks:
the address lives in a relationship file and the cell shows only link text, so a
reader of cell values sees no URL. Getting that right would take the same
calibration the PDF reader took, against a second extraction model with its own
artefact classes.

The other five are true of the file and misleading about the disclosure. A data
extract does not carry a fuel mix diagram's group headings, and reporting that
it does not, against a named utility, is the harm this project exists to refuse
arriving through a third door: not content hidden in a picture, not content the
extractor handed over in pieces, but content that was never supposed to be in
that file.

### What the regulation attaches the obligation to

Section 1393.1(i) provides that the Energy Commission generates the label or
supplies a template, and that the format may not be altered by the retail
supplier. It is the format that is fixed. The workbook is a different format,
published by the Energy Commission, described by the Energy Commission as an
alternative version. Two files in two formats are not one document because they
sit on one web page.

Section 1393.1(b)(2) requires the label to be provided to the Energy Commission
and displayed on the supplier's website. Which rendering a given supplier
displays is a fact about that supplier's website. It is not in either file.

### What the tool would have to know

This tool is offline and reads one file at a time. It cannot learn that two
files are a pair from the files: nothing in the PDF points at the workbook. It
could only learn it from the index page, which it does not fetch, or from an
operator asserting it on the command line. Option C would therefore report a
conclusion about a subject the operator defined, under a tool that names itself
as the author of the finding.

## Decision

**Option A.** The tool reads PDF and plain text. It does not read the workbook,
and it never treats two files as one label.

PCL004's finding is left exactly as it is, because it is already scoped
correctly. It says the words "do not appear in the extracted text", it carries
the extraction basis sentence naming this PDF, and it lists what appears
instead. It has never said that the disclosure lacks the name.

One thing changes at the point of use. A directory expands to the label formats
this tool reads and anything else in it was dropped in silence. It is now named:
the report ends with the files in the directories given that are not a format
this tool reads, and the JSON carries them as `skipped`. Someone who downloads
both files for a supplier and points the tool at the folder is told which one
the report is about. They are not in any count and naming one is not checking
it, so a folder holding nothing but workbooks still reports `NOTHING CHECKED`
and exits 3.

`docs/sources.md` keeps the finding that all four workbooks read name the
Commission in full and that none carries a telephone number, and the README
says the same in two sentences. That is the honest place for a fact about a
document this tool does not read.

## Consequences

The tool's subject stays one document, which is the thing that lets every
finding be a fact about a document.

A reader who wants to know whether the disclosure as a whole names the
regulator has the answer in `docs/sources.md` and does not have it from the
tool. That is the cost, and it is paid in the right direction: the tool
underclaims about a file it did not open rather than overclaiming about one it
did.

Option B stays available and this record is what it would have to answer.
Reading a workbook is not hard; calibrating a second extraction model so that
its artefacts do not become findings against named utilities is the work, and
ADR 0006 is the evidence for how much of it there is. Nothing about that work is
made easier by doing it in a hurry now.

Option C is refused and this record is where the argument would have to be
reopened. Merging two files into one subject requires the tool to be told they
are a pair, and a finding about an operator-defined subject is not a finding
about a document.
