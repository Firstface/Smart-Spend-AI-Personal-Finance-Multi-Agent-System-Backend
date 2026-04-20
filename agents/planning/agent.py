import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.orm import Session

# 导入你刚刚写好的 Service
from .service import PlanningService

logger = logging.getLogger(__name__)

class PlanningAgent:
    def __init__(self):
        self.service = PlanningService()
        # 使用轻量级模型进行意图解析，节省成本
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    async def handle(self, message: str, user_id: str, db: Session) -> str:
        """
        Agent 的主入口：解析消息 -> 决定操作 -> 调用服务 -> 返回文本
        """
        # 1. 内部解析：让 LLM 决定该调哪个接口
        analysis = self._parse_intent(message)
        action = analysis.get("action")
        month = analysis.get("month") or datetime.now().strftime("%Y-%m")
        feedback = analysis.get("feedback")

        logger.info(f"PlanningAgent: Action={action}, Month={month}, User={user_id}")

        try:
            # 2. 根据解析出的 action 分发任务
            if action == "view":
                return self._handle_view(db, user_id, month)
            
            elif action == "create":
                plans = self.service.generate_budget_plans(db, user_id, month)
                return self._format_plans_to_string(plans, "Generated New Plans")
            
            elif action == "refine":
                if not feedback:
                    return "I understood you want to change the plan, but could you specify what exactly should be adjusted? (e.g., 'Lower the dining budget')"
                
                plans = self.service.refine_budget_plans(db, user_id, month, feedback)
                return self._format_plans_to_string(plans, f"Refined Plans (based on: {feedback})")
            
            else:
                return "I'm not sure how to help with your budget planning. Try asking 'show my budget' or 'make a plan for next month'."

        except Exception as e:
            logger.error(f"PlanningAgent Error: {str(e)}")
            return "Sorry, I encountered an error while processing your budget request. Please try again later."
        


    def _parse_intent(self, message: str) -> Dict[str, Any]:
        """
        使用 LLM 将自然语言转为结构化指令
        """
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        prompt = ChatPromptTemplate.from_template("""
            You are a parsing assistant for a budget planning agent. 
            Current Date: {current_date}
            
            User Message: "{message}"
            
            Task:
            1. Determine the 'action': 
               - 'view': user wants to see their existing plans.
               - 'create': user wants to start/generate a new plan.
               - 'refine': user provides feedback/adjustments to an existing plan.
            2. Identify the 'month' in 'YYYY-MM' format. If it's "next month", calculate it based on Current Date.
            3. If the action is 'refine', extract the 'feedback' (the specific change the user wants).
            
            Return ONLY a JSON object:
            {{"action": "view"|"create"|"refine", "month": "YYYY-MM", "feedback": "string or null"}}
        """)
        
        chain = prompt | self.llm
        response = chain.invoke({"message": message, "current_date": current_date})
        
        try:
            # 兼容处理返回格式
            content = response.content if hasattr(response, 'content') else str(response)
            # 简单清理可能存在的 Markdown 格式
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
        except Exception:
            return {"action": "view", "month": None, "feedback": None}

    def _handle_view(self, db: Session, user_id: str, month: str) -> str:
        """
        处理查看逻辑：先查 Service 里的最新版本逻辑
        """
        plans = self.service.get_plans(db, user_id, month, latest_only=True)
        if not plans:
            return f"You don't have a budget plan for {month} yet. Would you like me to generate one?"
        return self._format_plans_to_string(plans, f"Current Plans for {month}")


    def _format_plans_to_string(self, plans: list, title: str) -> str:
        """
        将数据库对象/列表转为用户友好的聊天文本
        """
        if not plans:
            return "No plans found or generated."

        response = f"### 📊 {title}\n\n"
        for p in plans:
            # # 兼容处理：可能是 dict 也可能是 SQLAlchemy 对象
            # scenario = getattr(p, 'scenario', p.get('scenario', 'Unknown')).capitalize()
            # total = getattr(p, 'total_budget', p.get('total_budget', 0))
            # evidence = getattr(p, 'evidence', p.get('evidence', ''))
            # limits = getattr(p, 'category_limits', p.get('category_limits', {}))

            def get_val(obj, key, default=None):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            scenario = str(get_val(p, 'scenario', 'Unknown')).capitalize()
            total = get_val(p, 'total_budget', 0)
            evidence = get_val(p, 'evidence', '')
            limits = get_val(p, 'category_limits', {})

            # 处理 SQLAlchemy 的 JSON 字段可能是字符串的情况
            if isinstance(limits, str):
                try:
                    limits = json.loads(limits)
                except:
                    limits = {}

            response += f"**{scenario} Scenario**\n"
            response += f"- **Total Budget:** {total} SGD\n"
            if isinstance(limits, dict):
                for cat, limit in limits.items():
                    response += f"  - {cat}: {limit} SGD\n"
            response += f"- **Reasoning:** {evidence}\n\n"
        
        response += "---\n*You can ask me to adjust these plans by giving feedback like 'reduce dining' or 'increase entertainment budget'.*"
        return response