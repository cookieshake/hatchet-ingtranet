from datetime import datetime, timedelta, timezone
import logging
from textwrap import dedent
import json

from loguru import logger
from pydantic import BaseModel, Field
from hatchet_sdk import Context, ParentCondition
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate

from hatching import hatchet


classification_model = init_chat_model(
    "gpt-4o-mini",
    model_provider="openai"
)

class NriyV1Input(BaseModel):
    history: str
    input: str
    channel_id: str

wf = hatchet.workflow(name="nriy_v1", input_validator=NriyV1Input)

@wf.task()
async def get_now_context(input: NriyV1Input, ctx: Context):
    return {
        # datetime in KST timezone
        "현재시각": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),
    }

@wf.task()
async def analyze(input: NriyV1Input, ctx: Context):
    template = ChatPromptTemplate.from_template(dedent("""
        아래 텍스트를 보고, 주어진 형식의 출력값을 만들어주세요.
        {input}
    """))

    class Output(BaseModel):
        uses_profanity: bool = Field(
            description="Indicates whether the input text contains profanity or offensive language."
        )

    prompt = await template.ainvoke(input)
    logger.info(f"Prompt: {prompt}")
    result = await classification_model \
        .with_structured_output(Output) \
        .ainvoke(prompt)
    return result.model_dump()

@wf.task(
    parents=[analyze],
    skip_if=[
        ParentCondition(
            parent=analyze,
            expression="output.uses_profanity == false",
        )
    ]
)
async def skip_result(input: NriyV1Input, ctx: Context):
    return {
        "reply": False
    }

@wf.task(
    parents=[get_now_context, analyze],
    skip_if=[
        ParentCondition(
            parent=analyze,
            expression="output.uses_profanity == true",
        )
    ]
)
async def check_search_required(input: NriyV1Input, ctx: Context):
    template = ChatPromptTemplate.from_template(dedent("""
        당신은 여러 사람들이 참가해 있는 대화방에 들어와 있습니다.
        당신은 여러 사람들이 말하는 내용을 듣고, 알맞고 똑똑한 말을 대화방에서 할 수 있어야 합니다.
        대화의 흐름을 중요하게 여기세요.

        참고할 정보는 아래와 같습니다.
        ```
        {current_context}
        ```

        지금까지의 대화의 흐름은 아래와 같습니다.
        {history}

        당신은 아래 질문에 대해 대답해야합니다.
        {input}

        답변을 만들기에 앞서 필요한 정보를 모으려고 합니다.
        정확한 답변을 만들기 위해 필요한 행위를 잘 골라주세요.
        현재시간 정보를 잘 활용하세요.
    """))

    class Output(BaseModel):
        news_search: bool = Field(
            description="whether news search results would be helpful for answering"
        )
        blog_search: bool = Field(
            description="whether blog search results would be helpful for answering"
        )
        web_search: bool = Field(
            description="whether general web search results would be helpful for answering"
        )
        query_string: str = Field(
            description="suggested Korean search keyword or phrase to use if search is needed"
        )
    input_data = input.model_dump()
    input_data["current_context"] = json.dumps(await ctx.task_output(get_now_context))
    prompt = await template.ainvoke(input_data)
    result = await classification_model \
        .with_structured_output(Output) \
        .ainvoke(prompt)
    return result.model_dump()