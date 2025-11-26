from sqlalchemy import create_engine, select, MetaData
db_engine = create_engine("postgresql://librarymetadata_all:@localhost:5888/librarymetadata_all")

db_model = MetaData()
db_model.reflect(bind=db_engine)
db_model = db_model.tables

with db_engine.connect() as db_connection:
	result = db_connection.execute(select(db_model['meta_records']).where(db_model['meta_records'].c.id == 'ea236b90-0777-11e4-b1a4-005056827e52'))
	result = result.first()
	print(result.library)