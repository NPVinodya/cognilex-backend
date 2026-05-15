from fastapi import APIRouter
from controllers.message_Controller import (
    send_direct_message, 
    get_lawyer_messages, 
    get_user_messages_with_lawyer,
    mark_messages_as_read
)
from pydantic import BaseModel

router = APIRouter(prefix="/api/messages", tags=["Messages"])

class MessageCreate(BaseModel):
    user_id: str
    lawyer_id: str
    content: str
    sender_role: str = "user"

@router.post("/send")
async def send_msg(data: MessageCreate):
    return await send_direct_message(data.user_id, data.lawyer_id, data.content, data.sender_role)

@router.get("/lawyer/{lawyer_id}")
async def get_lawyer_msgs(lawyer_id: str):
    return await get_lawyer_messages(lawyer_id)

@router.get("/conversation/{user_id}/{lawyer_id}")
async def get_conv(user_id: str, lawyer_id: str):
    return await get_user_messages_with_lawyer(user_id, lawyer_id)

@router.post("/read/{lawyer_id}/{user_id}")
async def mark_read(lawyer_id: str, user_id: str):
    await mark_messages_as_read(lawyer_id, user_id)
    return {"success": True}
