from sqlalchemy import update
from sqlalchemy import exc
from semant_demo.schemas import Task, TasksBase

import logging

class DBError(Exception):
    pass

async def update_task_status(task_id: str, status: str, result={}, collection_name=None, session=None, all_texts_count=-1, processed_count=-1, tag_id=None, tag_processing_data=None):
        try:
            values_to_update = {
                "status": status
            }

            if collection_name is not None:
                values_to_update["collection_name"] = collection_name

            if result != {}:
                values_to_update["result"] = result

            if all_texts_count > -1:
                values_to_update["all_texts_count"] = int(all_texts_count)

            if processed_count > -1:
                values_to_update["processed_count"] = int(processed_count)    

            if tag_id is not None:
                values_to_update["tag_id"] = str(tag_id)

            if tag_processing_data is not None:
                values_to_update["tag_processing_data"] = tag_processing_data

            stmt = update(Task).where(Task.taskId == task_id).values(**values_to_update)
            
            # execute the update           
            await session.execute(stmt)
            await session.commit()

            logging.info("Data updated")
    
        except exc.SQLAlchemyError as e:
            logging.exception(f'Failed updating object in database. Task id ={task_id}')
            await session.rollback()  # rollback broken transaction
            raise DBError(f'Failed updating object in database. Task id ={task_id}') from e         