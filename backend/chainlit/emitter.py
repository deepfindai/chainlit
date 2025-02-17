import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, cast

from chainlit.data import get_data_layer
from chainlit.element import Element, File
from chainlit.logger import logger
from chainlit.message import Message
from chainlit.session import BaseSession, WebsocketSession
from chainlit.step import StepDict
from chainlit.types import (
    AskActionResponse,
    AskSpec,
    FileDict,
    FileReference,
    ThreadDict,
    UIMessagePayload,
)
from chainlit.user import PersistedUser
from socketio.exceptions import TimeoutError


class BaseChainlitEmitter:
    """
    Chainlit Emitter Stub class. This class is used for testing purposes.
    It stubs the ChainlitEmitter class and does nothing on function calls.
    """

    session: BaseSession

    def __init__(self, session: BaseSession) -> None:
        """Initialize with the user session."""
        self.session = session

    async def emit(self, event: str, data: Any):
        """Stub method to get the 'emit' property from the session."""
        pass

    async def ask_user(self):
        """Stub method to get the 'ask_user' property from the session."""
        pass

    async def resume_thread(self, thread_dict: ThreadDict):
        """Stub method to resume a thread."""
        pass

    async def send_step(self, step_dict: StepDict):
        """Stub method to send a message to the UI."""
        pass

    async def update_step(self, step_dict: StepDict):
        """Stub method to update a message in the UI."""
        pass

    async def delete_step(self, step_dict: StepDict):
        """Stub method to delete a message in the UI."""
        pass

    async def send_ask_timeout(self):
        """Stub method to send a prompt timeout message to the UI."""
        pass

    async def clear_ask(self):
        """Stub method to clear the prompt from the UI."""
        pass

    async def init_thread(self, interaction: str):
        pass

    async def process_user_message(self, payload: UIMessagePayload) -> Message:
        """Stub method to process user message."""
        return Message(content="")

    async def send_ask_user(
        self, step_dict: StepDict, spec: AskSpec, raise_on_timeout=False
    ) -> Optional[Union["StepDict", "AskActionResponse", List["FileDict"]]]:
        """Stub method to send a prompt to the UI and wait for a response."""
        pass

    async def update_token_count(self, count: int):
        """Stub method to update the token count for the UI."""
        pass

    async def task_start(self):
        """Stub method to send a task start signal to the UI."""
        pass

    async def task_end(self):
        """Stub method to send a task end signal to the UI."""
        pass

    async def stream_start(self, step_dict: StepDict):
        """Stub method to send a stream start signal to the UI."""
        pass

    async def send_token(self, id: str, token: str, is_sequence=False):
        """Stub method to send a message token to the UI."""
        pass

    async def set_chat_settings(self, settings: dict):
        """Stub method to set chat settings."""
        pass

    async def send_action_response(
        self, id: str, status: bool, response: Optional[str] = None
    ):
        """Send an action response to the UI."""
        pass


class ChainlitEmitter(BaseChainlitEmitter):
    """
    Chainlit Emitter class. The Emitter is not directly exposed to the developer.
    Instead, the developer interacts with the Emitter through the methods and classes exposed in the __init__ file.
    """

    session: WebsocketSession

    def __init__(self, session: WebsocketSession) -> None:
        """Initialize with the user session."""
        self.session = session

    def _get_session_property(self, property_name: str, raise_error=True):
        """Helper method to get a property from the session."""
        if not hasattr(self, "session") or not hasattr(self.session, property_name):
            if raise_error:
                raise ValueError(f"Session does not have property '{property_name}'")
            else:
                return None
        return getattr(self.session, property_name)

    @property
    def emit(self):
        """Get the 'emit' property from the session."""

        return self._get_session_property("emit")

    @property
    def ask_user(self):
        """Get the 'ask_user' property from the session."""
        return self._get_session_property("ask_user")

    def resume_thread(self, thread_dict: ThreadDict):
        """Send a thread to the UI to resume it"""
        return self.emit("resume_thread", thread_dict)

    def send_step(self, step_dict: StepDict):
        """Send a message to the UI."""
        return self.emit("new_message", step_dict)

    def update_step(self, step_dict: StepDict):
        """Update a message in the UI."""
        return self.emit("update_message", step_dict)

    def delete_step(self, step_dict: StepDict):
        """Delete a message in the UI."""
        return self.emit("delete_message", step_dict)

    def send_ask_timeout(self):
        """Send a prompt timeout message to the UI."""

        return self.emit("ask_timeout", {})

    def clear_ask(self):
        """Clear the prompt from the UI."""

        return self.emit("clear_ask", {})

    async def flush_thread_queues(self, interaction: str):
        if data_layer := get_data_layer():
            if isinstance(self.session.user, PersistedUser):
                user_id = self.session.user.id
            else:
                user_id = None
            try:
                await data_layer.update_thread(
                    thread_id=self.session.thread_id,
                    user_id=user_id,
                    metadata={"name": interaction},
                )
            except Exception as e:
                logger.error(f"Error updating thread: {e}")
            await self.session.flush_method_queue()

    async def init_thread(self, interaction: str):
        await self.flush_thread_queues(interaction)
        await self.emit("first_interaction", interaction)

    async def process_user_message(self, payload: UIMessagePayload):
        step_dict = payload["message"]
        file_refs = payload["fileReferences"]
        # UUID generated by the frontend should use v4
        assert uuid.UUID(step_dict["id"]).version == 4

        message = Message.from_dict(step_dict)
        # Overwrite the created_at timestamp with the current time
        message.created_at = datetime.utcnow().isoformat()

        asyncio.create_task(message._create())

        if not self.session.has_first_interaction:
            self.session.has_first_interaction = True
            asyncio.create_task(self.init_thread(message.content))

        if file_refs:
            files = [
                self.session.files[file["id"]]
                for file in file_refs
                if file["id"] in self.session.files
            ]
            file_elements = [Element.from_dict(file) for file in files]
            message.elements = file_elements

            async def send_elements():
                for element in message.elements:
                    await element.send(for_id=message.id)

            asyncio.create_task(send_elements())

        self.session.root_message = message

        return message

    async def send_ask_user(
        self, step_dict: StepDict, spec: AskSpec, raise_on_timeout=False
    ):
        """Send a prompt to the UI and wait for a response."""

        try:
            # Send the prompt to the UI
            user_res = await self.ask_user(
                {"msg": step_dict, "spec": spec.to_dict()}, spec.timeout
            )  # type: Optional[Union["StepDict", "AskActionResponse", List["FileReference"]]]

            # End the task temporarily so that the User can answer the prompt
            await self.task_end()

            final_res: Optional[
                Union["StepDict", "AskActionResponse", List["FileDict"]]
            ] = None

            if user_res:
                interaction = None
                if spec.type == "text":
                    message_dict_res = cast(StepDict, user_res)
                    await self.process_user_message(
                        {"message": message_dict_res, "fileReferences": None}
                    )
                    interaction = message_dict_res["output"]
                    final_res = message_dict_res
                elif spec.type == "file":
                    file_refs = cast(List[FileReference], user_res)
                    files = [
                        self.session.files[file["id"]]
                        for file in file_refs
                        if file["id"] in self.session.files
                    ]
                    final_res = files
                    interaction = ",".join([file["name"] for file in files])
                    if get_data_layer():
                        coros = [
                            File(
                                name=file["name"],
                                path=str(file["path"]),
                                mime=file["type"],
                                chainlit_key=file["id"],
                                for_id=step_dict["id"],
                            )._create()
                            for file in files
                        ]
                        await asyncio.gather(*coros)
                elif spec.type == "action":
                    action_res = cast(AskActionResponse, user_res)
                    final_res = action_res
                    interaction = action_res["value"]

                if not self.session.has_first_interaction and interaction:
                    self.session.has_first_interaction = True
                    await self.init_thread(interaction=interaction)

            await self.clear_ask()
            return final_res
        except TimeoutError as e:
            await self.send_ask_timeout()

            if raise_on_timeout:
                raise e
        finally:
            await self.task_start()

    def update_token_count(self, count: int):
        """Update the token count for the UI."""

        return self.emit("token_usage", count)

    def task_start(self):
        """
        Send a task start signal to the UI.
        """
        return self.emit("task_start", {})

    def task_end(self):
        """Send a task end signal to the UI."""
        return self.emit("task_end", {})

    def stream_start(self, step_dict: StepDict):
        """Send a stream start signal to the UI."""
        return self.emit(
            "stream_start",
            step_dict,
        )

    def send_token(self, id: str, token: str, is_sequence=False):
        """Send a message token to the UI."""
        return self.emit(
            "stream_token", {"id": id, "token": token, "isSequence": is_sequence}
        )

    def set_chat_settings(self, settings: Dict[str, Any]):
        self.session.chat_settings = settings

    def send_action_response(
        self, id: str, status: bool, response: Optional[str] = None
    ):
        return self.emit(
            "action_response", {"id": id, "status": status, "response": response}
        )
