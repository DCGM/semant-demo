The benchmarks as now are not efficient and test things which are not needed.
It is enough to do the tests with tags (user collections are not needed), and we just need to get information on:
- Latency and throughput of adding references to chunks
- Latency and throughput of removing references from chunks
- Speed of loading chunks with the tag and user collection fields

The tests should be performed with:
- varying concurency using single operations
- batch operations

Reported values should be:
- mean, median, P90, P99 for both individual operations and batch operations
- thoughput should be measure in chunks per second and it should sum all the concurrent operations together

Parameters of the test should be:
- Names of all the collections - Chunks, Tag - these can have specific names in a specific database.
- `Number of affected chunks` - the test should avoid to sample chunks in database order - should mix it up at least a little bit
- `Concurency counts` to be tested
- `Fullness levels` for references (how many references are stored in the chunks)
- `Operation count` number of inserted and deleted references per 

For efficiency, the tests should be performed like this:
0. Check that the collections exist and have enough chunks in them. Otherwise print error and exit.
1. Insert tags needed for the test
2. Add  references using the fastest batch operation available for the next `Fullness level`
3. Do concurency read test - all `Number of affected chunks
4. Do the batch read test - all `Number of affected chunks with batches of at most 100 chunks
3. Do concurency insertion test - insert `Operation count` references to `Number of affected chunks`
4. Do concurency deletion test - delete inserted references from step 3.
5. Do batch insertion test - single batch should add references for a single tag across all `Number of affected chunks`, should insert `Operation count` references
6. Do batch deletion test - delete references from step 5, again a single batch should include removal of a single tag from all `Number of affected chunks`
8. If not all `Fullness levels` done, move to step 2.
9. Delete all inserted tags and references again using efficient batch operations.\
10. Render plots, generate report, print result tables



