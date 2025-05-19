from pydantic import BaseModel

class AppointmentCreate(BaseModel):
    full_name: str
    phone_number: str
    address: str
    car_model: str
    issue_description: str
    preferred_datetime: str