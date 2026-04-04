from datetime import datetime, date, time


class AppointmentModel:
    """Appointment model for MongoDB"""

    @staticmethod
    def create_appointment_dict(
            lawyer_id: str,
            client_id: str,
            appointment_date: date,
            appointment_time: time,
            appointment_type: str,
            notes: str = None
    ) -> dict:
        """Create appointment document"""
        return {
            "lawyer_id": lawyer_id,
            "client_id": client_id,
            "date": appointment_date.isoformat(),
            "time": appointment_time.isoformat(),
            "appointment_type": appointment_type,
            "status": "pending",
            "notes": notes,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }

    @staticmethod
    def appointment_response(appointment: dict, lawyer_name: str, client_name: str) -> dict:
        """Format appointment response"""
        return {
            "id": str(appointment["_id"]),
            "lawyer_id": str(appointment["lawyer_id"]),
            "lawyer_name": lawyer_name,
            "client_id": str(appointment["client_id"]),
            "client_name": client_name,
            "date": appointment["date"],
            "time": appointment["time"],
            "appointment_type": appointment["appointment_type"],
            "status": appointment["status"],
            "notes": appointment.get("notes"),
            "created_at": appointment["created_at"]
        }