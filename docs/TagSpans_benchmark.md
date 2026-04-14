# Benchmarks for Tag Spans API

## Variants

- **embedded** - Table Chunks_test contains a field tagSpansArr, which is an array of spans that belong to the chunk
- **separate** - New table TagSpans_test contains spans that reference the chunk they belong to

## Tests

### Get Tag Spans for a single Chunk

- **blue** - embedded
-   - `GET /tag_spans/{{chunk_id}}?mode=embedded`
- **green** - separate
-   - `GET /tag_spans/{{chunk_id}}?mode=separate`

```mermaid
xychart-beta
    title "Get 100 Tag Spans"
    x-axis "Test number" [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y-axis "Response time (ms)" 0 --> 300
    line [45, 41, 73, 43, 75, 79, 53, 80, 68, 75]
    line [45, 55, 41, 47, 74, 43, 257, 70, 55, 164]
```

### Create Tag Spans

- **blue** - embedded
-   - `POST /tag_spans/, body: {mode: "embedded", spans: [number_of_spans]}`
- **green** - separate
-   - `POST /tag_spans/, body: {mode: "separate", spans: [number_of_spans]}`

```mermaid
xychart-beta
    title "Create 1 Tag Span"
    x-axis "Test number" [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y-axis "Response time (ms)" 0 --> 300
    line [93, 47, 33, 41, 35, 38, 39, 61, 133, 40]
    line [88, 106, 133, 88, 178, 177, 131, 139, 79, 99]
```

```mermaid
xychart-beta
    title "Create 100 Tag Spans"
    x-axis "Test number" [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y-axis "Response time (ms)" 0 --> 7000
    line [100, 48, 41, 41, 54, 44, 58, 39, 38, 41]
    line [6220, 3430, 5020, 3370, 6140, 6340, 610, 3410, 6250, 5610]
```

### Update Tag Span

- **blue** - embedded
-   - `PATCH /tag_spans/update, body: {mode: "embedded", index: span_index, tagId: "new_tag_id"}`
- **green** - separate
-   - `PATCH /tag_spans/update, body: {mode: "separate", span_id: "span_id", tagId: "new_tag_id"}`

```mermaid
xychart-beta
    title "Change informations in Tag Span"
    x-axis "Test number" [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y-axis "Response time (ms)" 0 --> 800
    line [174, 525, 784, 153, 103, 470, 113, 94, 122, 77]
    line [228, 81, 300, 49, 39, 43, 58, 49, 45, 84]
```

## Conclusion

- Getting Tag Spans for a single chunk is faster in the embedded variant - response times around 40-80 ms, separate variant around 40-250 ms.
- Creating Tag Spans is significantly faster in the embedded variant - response times around 30-60 ms for creating 1 span and around 40-60 ms for creating 100 spans, separate variant around 80-180 ms for creating 1 span and 600-6300 ms for creating 100 spans.
- Updating Tag Spans is faster in the separate variant - response times around 40-80 ms, separate version around 100-800 ms for the embedded variant.

Overall, the **embedded** variant performs better for **retrieving and creating Tag Spans**, while the **separate** variant performs better for **updating Tag Spans**.
