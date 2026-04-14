import os
import logging
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from models.budget_plans import BudgetPlan
from schemas.planning import BudgetPlanCreate
from typing import List, Dict, Any
from decimal import Decimal
import json
from sqlalchemy import func

# Setup logging
logger = logging.getLogger(__name__)

class PlanningService:
    def __init__(self):
        # Defaulting to GPT-4o for high-reasoning tasks like financial planning.
        # Ensure OPENAI_API_KEY is set in your .env file.
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.2)
        # We expect a list of plans (Conservative, Balanced, Aggressive)
        self.parser = JsonOutputParser(pydantic_object=BudgetPlanCreate)

    def _get_latest_version(self, db:Session, user_id: str, month: str ) -> int:
        # 获取当前用户在该月份的最新版本号
        max_version = db.query(func.max(BudgetPlan.version)).filter(
            BudgetPlan.user_id == user_id,
            BudgetPlan.plan_month == month
        ).scalar()
        return max_version if max_version is not None else 0


    def generate_budget_plans(self, db: Session, user_id: str, month: str) -> List[dict]:
        """
        Generates three budget scenarios based on previous month's insights.
        """
        # 1. Fetch Insights (Placeholder: In production, retrieve data from Song Mingzheng's 'insights_reports' table)
        # Example logic: last_report = db.query(InsightReport).filter_by(user_id=user_id).first()
        # 需要从数据库获取数据，大概需要对获取到的数据进行整理，要针对uid进行获取最新的报告
        # 需要和分类的类名对齐
        context_data = (    # 测试数据
            "Last month total expenditure: 3,000 SGD. "
            "Breakdown: Dining 1,200 SGD (Overspent), Housing 1,000 SGD (Fixed), "
            "Transport 300 SGD, Entertainment 500 SGD."
        )

        # 2. Construct the Prompt with strict English constraints
        prompt = ChatPromptTemplate.from_template("""
            You are a professional Financial Planning Agent. Based on the user's spending context, 
            generate three distinct monthly budget scenarios for the upcoming month.
            
            User Context: {context}
            
            Requirements:
            1. Principle: Strictly follow the 50/30/20 rule (50% Needs, 30% Wants, 20% Savings).
            2. Scenarios: Provide exactly three scenarios: 'conservative' (max savings), 
               'balanced' (standard 50/30/20), and 'aggressive' (higher allowance for 'wants' while maintaining core savings).
            3. Currency: All values must be in SGD.
            4. Categories: Use standardized categories: 'Dining', 'Housing', 'Transport', 'Entertainment', 'Others'.
            5. Evidence: For each scenario, provide a brief English explanation of why the limits were set.
            6. Output Format: Each scenario MUST be a JSON object containing:
       - 'scenario': (conservative | balanced | aggressive)
       - 'total_budget': (number)
       - 'savings_target': (number)
       - 'category_limits': (dict)
       - 'evidence': (string, mandatory reasoning why these limits fit the scenario)
       
    {format_instructions}
        """)

        # 3. Execution Chain
        chain = prompt | self.llm | self.parser
        
        try:
            # Generate the plans via LLM
            plans = chain.invoke({
                "context": context_data,
                "format_instructions": self.parser.get_format_instructions()
            })
            
            # 4. Persistence (Optional: Save to DB here or in the API layer)
            # For each plan in plans: 
            #    new_entry = BudgetPlan(**plan, user_id=user_id, plan_month=month)
            #    db.add(new_entry)
            # db.commit()
            
            return self._validate_and_save(db, user_id, month, plans)
        except Exception as e:
            logger.error(f"Failed to generate budget plans: {str(e)}")
            return []
        
    def refine_budget_plans(self, db: Session, user_id: str, month: str, user_feedback: str) -> List[BudgetPlan]:
        # 1. 获取最新版本的旧计划作为上下文
        latest_v = self._get_latest_version(db, user_id, month)
        logger.info(f"Latest plan version for user {user_id} in month {month} is {latest_v}")
        if latest_v == 0:
            # 如果根本没有旧计划，则退化为普通生成逻辑
            return self.generate_budget_plans(db, user_id, month)

        old_plans = db.query(BudgetPlan).filter_by(user_id=user_id, plan_month=month, version=latest_v).all()
        
        # 将旧计划格式化为字符串，传给 LLM 
        old_plans_context = "\n".join([
            f"Scenario {p.scenario}: Total {p.total_budget}, Limits: {p.category_limits}" 
            for p in old_plans
        ])

        # 2. 构建“追问”提示词
        refine_prompt = ChatPromptTemplate.from_template("""
           You are a Financial Expert. The user wants to update their budget.
        
            [Previous Plans]: {old_plans_context}
            [User Feedback]: "{feedback}"
        
            Requirements:
            1. Create 3 new scenarios: 'conservative', 'balanced', 'aggressive'.
            2. MANDATORY: The 'evidence' field for each scenario MUST explain exactly how you adjusted 
                the limits based on the feedback: "{feedback}". Do not use generic templates.
            3. Keep values in SGD.
        
        {format_instructions}
        """)

        # 3. 调用 LLM 并保存（版本号 + 1）
        chain = refine_prompt | self.llm | self.parser
        new_raw_plans = chain.invoke({
            "version": latest_v,
            "old_plans_context": old_plans_context,
            "feedback": user_feedback,
            "format_instructions": self.parser.get_format_instructions()
        })

        # 在保存时，传入 new_version = latest_v + 1
        return self._validate_and_save(db, user_id, month, new_raw_plans, version=latest_v + 1)
        
    def _validate_and_save(self, db: Session, user_id: str, month: str, raw_plans: Any, version: int = 1) -> List[BudgetPlan]: 
        db_objects = []
        plans_to_process = []
        
        # 1. 彻底规避字符串迭代风险
        if isinstance(raw_plans, dict):
            # 情况 A: 返回的是 {"scenarios": [...]}
            if "scenarios" in raw_plans:
                plans_to_process = raw_plans["scenarios"]
            # 情况 B: 返回的是 {"conservative": {...}, ...} 
            # 你的日志显示目前是这种情况，我们必须手动转成 list
            else:
                for s_name, s_data in raw_plans.items():
                    if isinstance(s_data, dict):
                        s_data["scenario"] = s_name # 把 Key 塞进数据里
                        plans_to_process.append(s_data)
        elif isinstance(raw_plans, list):
            plans_to_process = raw_plans

        # 2. 遍历我们辛苦构建出来的 plans_to_process 列表
        for plan_dict in plans_to_process:
            # 即使走到这里，我们也要再加一道防线
            if not isinstance(plan_dict, dict):
                continue 

            try:
                # 1. 提取或计算 total_budget
                # 如果 LLM 没给 total_budget，我们就把所有数字加起来作为总预算
                if not plan_dict.get("evidence"):
                    scenario = plan_dict.get("scenario", "standard")
                    plan_dict["evidence"] = f"Budget plan generated based on {scenario} financial strategy."
                if "total_budget" not in plan_dict:
                    all_numbers = [v for v in plan_dict.values() if isinstance(v, (int, float, Decimal))]
                    plan_dict["total_budget"] = sum(all_numbers)

                # 2. 提取 category_limits
                # 如果 LLM 把 Dining, Housing 等直接放外面了，我们要把它们塞进 category_limits 字典
                if "category_limits" not in plan_dict:
                    standard_categories = ['Dining', 'Housing', 'Transport', 'Entertainment', 'Others']
                    # 找出字典中属于标准分类的项
                    plan_dict["category_limits"] = {
                        k: v for k, v in plan_dict.items() 
                        if k in standard_categories
                    }
                # 注入元数据
                plan_dict["user_id"] = str(user_id)
                plan_dict["plan_month"] = month
                plan_dict["version"] = version

                if "scenario" not in plan_dict:
                    plan_dict["scenario"] = "balanced"

                # Pydantic 校验与保存
                validated = BudgetPlanCreate(**plan_dict)
                db_plan = BudgetPlan(**validated.model_dump())
                db.add(db_plan)
                db_objects.append(db_plan)
            except Exception as e:
                logger.warning(f"Scenario validation error: {e}")
                continue

        # 3. 提交数据库
        if db_objects:
            try:
                db.commit()
                for obj in db_objects: db.refresh(obj)
                return db_objects
            except Exception as db_err:
                db.rollback()
                logger.error(f"DB Error: {db_err}")
        
        return []