from models.appointment import AppointmentModel

async def add_appointment_to_db(db, appointment_data: dict):
    result = await db.appointments.insert_one(appointment_data)
    return str(result.inserted_id)

async def get_lawyer_appointments(db, lawyer_id: str):
    appointments = []
    cursor = db.appointments.find({"lawyer_id": lawyer_id})
    async for doc in cursor:
        formatted_doc = AppointmentModel.appointment_response(
            doc, lawyer_name="Atty. Prabani", client_name="Nimal Silva"
        )
        appointments.append(formatted_doc)
    return appointments