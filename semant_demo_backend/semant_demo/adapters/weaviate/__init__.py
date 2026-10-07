"""Weaviate repositories: queries, filters, mapping to application schemas.

Repositories take ``UUID`` ids, return application schemas (never SDK objects), return
``None`` from single-object reads of a missing object and raise
``semant_demo.core.errors.NotFoundError`` when an operation needs an object that does not
exist. SDK errors are not wrapped. A repository implements only the operations it
supports; there is no common CRUD base class.
"""
