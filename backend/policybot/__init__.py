"""PolicyBot - a grounded, verifiable airline policy assistant.

Built to avoid the failure in Moffatt v. Air Canada (2024 BCCRT 149), where an
airline chatbot invented a refund rule that contradicted the airline's own
published policy, and the airline was held liable for what the bot said.
"""

from .engine import PolicyAssistant, AssistantReply

__all__ = ["PolicyAssistant", "AssistantReply"]
__version__ = "1.0.0"
