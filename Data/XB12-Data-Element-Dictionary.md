# XB12 INSTRUCTIONAL-MATERIAL-COST

**Source:** California Community Colleges Management Information System — Data Element Dictionary, Section Data Elements

**DED#:** XB12  
**Data Element Name:** INSTRUCTIONAL-MATERIAL-COST  
**Format:** X (single character)

## Description

This element indicates the cost of course materials for the section. The instructional material definition in Title 5 is more broadly defined; however, for the purpose of this data element, only the cost of course textbooks (including lab manuals) and supplementary materials (including software and homework systems) are to be reported.

**Open Education Resources (OER)** are those educational resources that reside in the public domain or have been released under an intellectual property license, such as a Creative Commons license, that permits their free use and repurposing by others.

## Coding Values

| Code | Meaning |
|------|---------|
| A | Section has no associated course material |
| ~~B~~ | ~~Section uses only no-cost digital instructional material~~ *(removed Summer 2024)* |
| C | Section has course material costs none of which are passed on to students |
| D | Section has low course material costs (as defined locally) |
| E | Section uses only no-cost, OER course material |
| F | Section uses only no-cost digital course material that does not meet OER guidelines |
| G | Section uses a mix of no-cost OER and other cost bearing resources, but no costs are passed to the student |
| Y | Section does not meet no-cost or low-cost course material criteria |

## Processing Edits

**FIELD CHECK:** A, C, D, E, F, G, Y

## Change History

| When | Change |
|------|--------|
| Summer 2022 | Implemented |
| Summer 2024 | Added clarifying language distinguishing "course materials" from instructional materials as defined in Title 5. Removed "B - Section uses only no-cost digital instructional material". Added E, F, G to better distinguish between different types of no-cost instructional materials and to add a category where the section may use a mix of no-cost OER and other course materials. |
