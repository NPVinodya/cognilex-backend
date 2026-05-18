from datetime import datetime


class MessageModel:
    """Message model for MongoDB"""

    @staticmethod
    def create_message_dict(
            conversation_id: str,
            sender: str,
            text: str,
            citation: dict | None = None
    ) -> dict:
        """Create message document"""
        doc = {
            "conversation_id": conversation_id,
            "sender": sender,
            "text": text,
            "created_at": datetime.utcnow()
        }

        if citation:
            doc.update({
                "citation_source": citation.get("source"),
                "citation_section": citation.get("section"),
                "citation_link": citation.get("link"),
                "citation_relevance": citation.get("relevance")
            })

        return doc

    @staticmethod
    def message_response(message: dict) -> dict:
        """Format message response"""
        result = {
            "id": str(message["_id"]),
            "sender": message["sender"],
            "text": message["text"],
            "created_at": message["created_at"]
        }

        if message.get("citation_source"):
            result["citation"] = {
                "source": message["citation_source"],
                "section": message["citation_section"],
                "link": message["citation_link"],
                "relevance": message.get("citation_relevance")
            }

        return result
