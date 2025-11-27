from sqlalchemy import create_engine, select, MetaData
db_engine = create_engine("postgresql://librarymetadata_all:@localhost:5888/librarymetadata_all")

db_model = MetaData()
db_model.reflect(bind=db_engine)
db_model = db_model.tables

def extractYear(dateIssued):
	return dateIssued

def map_result_names(result):
	res_dict = {}
	metadata = result.metadata_json

	#res_dict['library'] = result.library
	#res_dict['metadata_json'] = result.metadata_json

	# already in weaviate
	res_dict["title_main"]= result.title
	res_dict["title"]= metadata.get('Title', None)
	res_dict["subtitle"]= metadata.get('Subtitle', None)
	res_dict["partNumber"]=  metadata.get('PartNumber', None)
	res_dict["partName"]=  metadata.get('PartName', None)
	res_dict["dateIssued"]=  metadata.get('DateIssued', None) #parsed_filename["date"] + "T16:00:00+00:00",
	res_dict["yearIssued"]= extractYear(metadata.get('DateIssued', None))
	res_dict["author"]=  metadata.get('Author', None)
	res_dict["publisher"] =  metadata.get('Publisher', None)
	res_dict["language"] =  metadata.get('Language', None)
	# missing: res_dict["description"]: "",
	res_dict['url'] = result.id
	res_dict['public'] = result.public
	res_dict['documentType'] = result.record_type
	# res_dict['missing'] = 
	# missing: res_dict["genre"] = 
	res_dict["placeOfPublication"] =  metadata.get('PlaceTerm', None)
	
	# not yet in weaviate
	res_dict["SeriesName"] =  metadata.get('SeriesName', None)
	res_dict["SeriesNumber"] =  metadata.get('SeriesNumber', None)
	res_dict["Edition"] =  metadata.get('Edition', None)
	res_dict["ManufacturePublisher"] =  metadata.get('ManufacturePublisher', None)
	res_dict["ManufacturePlaceTerm"] =  metadata.get('ManufacturePlaceTerm', None)
	res_dict["Illustrator"] =  metadata.get('Illustrator', None)
	res_dict["Translator"] =  metadata.get('Translator', None)
	res_dict["Editor"] =  metadata.get('Editor', None)
	res_dict["Redaktor"] =  metadata.get('Redaktor', None)

	# parent_id | parent_library | public | order | record_type | page_type  | date | number | start_date  | end_date |image_path | mods_path | page_xml_path | metadata_json | page_placement | created_date | updated_date
	return res_dict

with db_engine.connect() as db_connection:
	#result = db_connection.execute(select(db_model['meta_records']).limit(10)) #(select(db_model['meta_records']).where(db_model['meta_records'].c.id == 'ea236b90-0777-11e4-b1a4-005056827e52'))
	result = db_connection.execute(select(db_model['meta_records'])
								.where(db_model['meta_records'].c.metadata_json.is_not(None))
								.limit(10)) #(select(db_model['meta_records']).where(db_model['meta_records'].c.id == 'ea236b90-0777-11e4-b1a4-005056827e52'))
	
	result = result.all()#first()
	print(result[0])#.library)
	print(map_result_names(result[0]))

"""

(semant) C:\Users\marti\Music\semANT_public\semant-demo\weaviate_utils>python sql.py
(UUID('f93beaf0-7807-11dc-a047-000d606f5dc6'), 'nkp', UUID('110df4e0-7801-11dc-908d-000d606f5dc6'), 'nkp', True, 27, 'periodicalitem', None, '11.8.1866', '29', datetime.datetime(1866, 8, 11, 0, 0), None, None, '/mnt/matylda0/ihradis/digiknihovna_public/nkp/c8ee2480-769f-11dc-bd8b-000d606f5dc6.mods/f93beaf0-7807-11dc-a047-000d606f5dc6.mods', None, {'Title': [[], ['Nikolsburger Wochenschrift für landwirtschaftliche, gemeinnützige Interessen und Unterhaltung.'], ['Nikolsburger Wochenschrift für la ... (90 characters truncated) ... zxx'], ['zxx']], 'Publisher': [[], [], ['Johan Bezdieka']], 'DateIssued': [['11.8.1866'], ['1866'], ['1860-1878']], 'PartNumber': [['29'], ['7'], []]}, 'Nikolsburger Wochenschrift für landwirtschaftliche, gemeinnützige Interessen und Unterhaltung.. 29', None, datetime.datetime(2025, 11, 26, 16, 58, 17, 580905), datetime.datetime(2025, 11, 26, 16, 58, 17, 580905))
nkp
{'title_main': 'Nikolsburger Wochenschrift für landwirtschaftliche, gemeinnützige Interessen und Unterhaltung.. 29', 'title': [[], ['Nikolsburger Wochenschrift für landwirtschaftliche, gemeinnützige Interessen und Unterhaltung.'], ['Nikolsburger Wochenschrift für landwirtschaftliche, gemeinnützige Interessen und Unterhaltung.']], 'subtitle': None, 'partNumber': [['29'], ['7'], []], 'partName': None, 'dateIssued': [['11.8.1866'], ['1866'], ['1860-1878']], 'yearIssued': [['11.8.1866'], ['1866'], ['1860-1878']], 'author': None, 'publisher': [[], [], ['Johan Bezdieka']], 'language': [['zxx'], ['zxx'], ['zxx']], 'url': UUID('f93beaf0-7807-11dc-a047-000d606f5dc6'), 'public': True, 'documentType': 'periodicalitem', 'placeOfPublication': None, 'SeriesName': None, 'SeriesNumber': None, 'Edition': None, 'ManufacturePublisher': None, 'ManufacturePlaceTerm': None, 'Illustrator': None, 'Translator': None, 'Editor': None, 'Redaktor': None}

"""