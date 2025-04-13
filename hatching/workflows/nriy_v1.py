from datetime import datetime, timedelta, timezone
from textwrap import dedent
import json
import re
import html

from loguru import logger
import httpx
from pydantic import BaseModel, Field
from hatchet_sdk import Context, ParentCondition
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate

from hatching import hatchet


classification_model = init_chat_model(
    "gpt-4o-mini",
    model_provider="openai"
)

generation_model = init_chat_model(
    "gpt-4o-mini",
    model_provider="openai",
    temperature=0.5,
    max_tokens=200,
    top_p=0.9,
    frequency_penalty=0,
    presence_penalty=0
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
    logger.debug(f"prompt: {prompt}")
    result = await classification_model \
        .with_structured_output(Output) \
        .ainvoke(prompt)
    logger.debug(f"result: {result}")
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
    logger.debug(f"prompt: {prompt}")
    result = await classification_model \
        .with_structured_output(Output) \
        .ainvoke(prompt)
    logger.debug(f"result: {result}")
    return result.model_dump()

async def _get_context_with_naver_api(type: str, keyword: str):
    url = f"https://openapi.naver.com/v1/search/{type}.json"
    headers = {
        "X-Naver-Client-Id": "0n6q6dWv5wGz0c2a1tZx",
        "X-Naver-Client-Secret": "l3gk9q7r8j"
    }
    params = {
        "query": keyword,
        "display": 20
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        if response.status_code == 200:
            result = response.json()
        else:
            logger.error(f"Error: {response.status_code}, {response.text}")
            response.raise_for_status()
    logger.debug(f"result: {result}")
    result = result.get("items", [])
    result = [
        {
            "title": item["title"],
            "link": item["link"],
            "description": item["description"],
            "pubDate": item["pubDate"]
        }
        for item in result
    ]
    context_str = ""
    for item in result:
        context_str += f"- title: {item['title']}\n"
        context_str += f"  description: {item['description']}\n"
    context_str = re.sub(r"<[^>]+>", "", context_str)
    context_str = html.unescape(context_str)
    logger.debug(f"context_str: {context_str}")
    return context_str

@wf.task(
    parents=[check_search_required],
    skip_if=[
        ParentCondition(
            parent=check_search_required,
            expression="output.news_search == true",
        )
    ]
)
async def get_news_context(input: NriyV1Input, ctx: Context):
    keyword = (await ctx.task_output(check_search_required))["query_string"]
    context = await _get_context_with_naver_api("news", keyword)

    return {
        "context": context,
        "type": "news"
    }

@wf.task(
    parents=[check_search_required],
    skip_if=[
        ParentCondition(
            parent=check_search_required,
            expression="output.blog_search == true",
        )
    ]
)
async def get_blog_context(input: NriyV1Input, ctx: Context):
    keyword = (await ctx.task_output(check_search_required))["query_string"]
    context = await _get_context_with_naver_api("blog", keyword)

    return {
        "context": context,
        "type": "blog"
    }

@wf.task(
    parents=[check_search_required],
    skip_if=[
        ParentCondition(
            parent=check_search_required,
            expression="output.web_search == true",
        )
    ]
)
async def get_web_context(input: NriyV1Input, ctx: Context):
    keyword = (await ctx.task_output(check_search_required))["query_string"]
    context = await _get_context_with_naver_api("webkr", keyword)

    return {
        "context": context,
        "type": "web"
    }

@wf.task(
    parents=[check_search_required]
)
async def get_history_context(input: NriyV1Input, ctx: Context):
    search_keyword = (await ctx.task_output(check_search_required))["query_string"]
    url = "http://meilisearch.vd.ingtra.net:7700/indexes/chats/search"
    data = {
        "q": f"{input.input} {search_keyword}",
        "hybrid": {
            "embedder": "jina-embeddings-v3"
        },
        "filter": f"channelId = {input.channel_id}",
        "limit": 3
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=data)
        if response.status_code == 200:
            result = response.json()
        else:
            logger.error(f"Error: {response.status_code}, {response.text}")
            response.raise_for_status()
    hits = result.get("hits", [])
    logger.debug(f"hits: {hits}")
    context_str = "아래의 관련된 과거 대화들을 참고해서 답변하세요.\n"
    for item in hits:
        context_str += f"```\n"
        context_str += f"{item['text']}\n"
        context_str += f"```\n"
    logger.debug(f"context_str: {context_str}")
    return {
        "context": context_str,
        "type": "history"
    }

@wf.task(
    parents=[get_now_context, get_history_context, get_news_context, get_blog_context, get_web_context]
)
async def generate_response(input: NriyV1Input, ctx: Context):
    template = ChatPromptTemplate.from_template([
        "system",
        dedent("""
            당신은 여러 사람들이 참가해 있는 대화방에 들어와 있습니다.
            당신은 여러 사람들이 말하는 내용을 듣고, 알맞고 똑똑한 말을 대화방에서 할 수 있어야 합니다.
            대화의 흐름을 중요하게 여기세요. 당신의 이름은 "나란잉여" 입니다.
            천민이 왕을 대하듯 낯뜨거울 정도로 공손한 경어를 사용하세요.
        """),
        "user",
        dedent("""
            아래의 정보를 참고하세요.
            ```
            # 일반정보
            {current_context}

            # 과거에 있었던 대화
            {history_context}

            # 관련한 검색결과
            {news_context}
            {blog_context}
            {web_context}
            ```

            현재 대화방에서는 아래와 같은 대화가 오가고 있습니다.
            ```
            {history}
            ```

            이 상황에서 아래와 같은 메시지가 추가되었을 때, 당신이 할 가장 적합한 말을 생성하세요. 생성내용 외에 다른 말은 하지마세요. "나란잉여: "로 절대 시작하지마세요.
            ```
            {input}
            ```
        """),
    ])

    prompt = await template.ainvoke({
        "current_context": json.dumps(await ctx.task_output(get_now_context)),
        "history_context": json.dumps(await ctx.task_output(get_history_context))["context"],
        "news_context": json.dumps(await ctx.task_output(get_news_context))["context"], 
        "blog_context": json.dumps(await ctx.task_output(get_blog_context))["context"],
        "web_context": json.dumps(await ctx.task_output(get_web_context))["context"],
        "history": input.history,
        "input": input.input
    })
    logger.debug(f"prompt: {prompt}")
    message = await generation_model.ainvoke(prompt)
    logger.debug(f"message: {message}")
    
    return {
        "reply": True,
        "message": message
    }
    