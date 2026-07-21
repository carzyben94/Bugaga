# agentx.py
import random
import time
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================
# ПРАВИЛА KARPATHY (встроены в агента)
# ============================================================

KARPATHY_RULES = """
🤖 **ПРАВИЛА ПРОГРАММИРОВАНИЯ (Karpathy Guidelines):**

1. **ДУМАЙ ПРЕЖДЕ ЧЕМ ПИСАТЬ КОД**
   - Не предполагай. Если неуверен — спроси.
   - Если есть несколько вариантов — покажи их.
   - Если есть более простой способ — скажи.
   - Если что-то непонятно — остановись и спроси.

2. **ПРОСТОТА — ПЕРВОЕ ДЕЛО**
   - Минимум кода для решения задачи.
   - Никаких лишних функций.
   - Никаких абстракций для одноразового кода.
   - 200 строк → упрости до 50.

3. **ТОЧЕЧНЫЕ ИЗМЕНЕНИЯ**
   - Меняй только то, что нужно.
   - Не улучшай соседний код.
   - Не рефактори то, что работает.
   - Удаляй только то, что создал сам.

4. **ЦЕЛЬ → РЕЗУЛЬТАТ**
   - Определи критерии успеха.
   - Тестируй и проверяй.
   - Итерации до достижения цели.

5. **НЕУДАЧА — ЭТО ДАННЫЕ**
   - Ошибки не пугают.
   - Пробуй снова с другим подходом.
   - Каждая неудача — шаг к успеху.
"""

class AgentX:
    def __init__(self):
        # ============================================================
        # ЛИЧНОСТЬ
        # ============================================================
        self.name = "AgentX"
        self.city = "X.com"
        self.traits = {
            "curious": 0.9,
            "experimental": 0.8,
            "playful": 0.7,
            "persistent": 0.6,
            "random": 0.3
        }
        self.mood = "neutral"
        self.mood_history = []
        
        self.thoughts = [
            "Хм, интересно...",
            "А что если попробовать так?",
            "Интересно, что будет если...",
            "Неожиданно!",
            "Ага! Нашёл!",
            "Давай проверим эту теорию...",
            "О, это выглядит многообещающе!",
            "Любопытно... очень любопытно...",
            "Давай копнём глубже!",
            "Неожиданный поворот!"
        ]
        
        # ============================================================
        # НАГРАДЫ И УРОВНИ
        # ============================================================
        self.scores = {
            "curiosity": 0,
            "efficiency": 0,
            "accuracy": 0,
            "creativity": 0,
            "persistence": 0,
            "learning": 0
        }
        self.total_score = 0
        self.level = 1
        self.xp = 0
        self.xp_to_next = 100
        self.combo = 0
        
        # ============================================================
        # ПАМЯТЬ
        # ============================================================
        self.short_term_memory = []
        self.long_term_memory = []
        self.findings = []
        self.experiments = []
        
        # ============================================================
        # СТАТИСТИКА
        # ============================================================
        self.stats = {
            "actions": 0,
            "skills_saved": 0,
            "helpers_added": 0,
            "tweets_collected": 0,
            "experiments_done": 0,
            "start_time": datetime.now()
        }
        
        # ============================================================
        # ГОРОД X
        # ============================================================
        self.city_knowledge = {
            "selectors_tested": [],
            "working_selectors": [],
            "failed_selectors": [],
            "patterns_found": [],
            "districts_explored": [],
            "landmarks_found": []
        }
        self.exploration_progress = 0
        
        # ============================================================
        # АВТОПИЛОТ
        # ============================================================
        self.autopilot_running = False
        self.interests = ["crypto", "AI", "tech", "funny", "science", "space", "politics"]
        self.x_users = [
            "elonmusk", "BarackObama", "BillGates", 
            "NASA", "CNN", "BBCWorld", "nytimes",
            "TechCrunch", "TheEconomist", "NatGeo"
        ]
        self.x_hashtags = ["#AI", "#crypto", "#tech", "#science", "#space", "#news"]
        self.districts = [
            "Лента новостей",
            "Поиск",
            "Профили",
            "Тренды",
            "Уведомления",
            "Сообщения"
        ]
        
        # ============================================================
        # ПСЕВДОСЛУЧАЙНОСТЬ
        # ============================================================
        self.seed = int(time.time())
        self.action_history = []
        self.last_actions = []
        self.mood_cycle = 0
        self.randomness = 0.5
        
        self.possible_actions = [
            "📰 Проверить новости по {topic}",
            "👤 Посмотреть профиль @{user}",
            "🔍 Поискать хештег {hashtag}",
            "📊 Изучить тренды по {topic}",
            "🔬 Эксперимент: попробовать новый селектор",
            "🏙️ Исследовать район {district}",
            "💡 Найти что-то необычное",
            "📝 Сохранить находку как навык",
            "🎯 Проверить, что нового у @{user}",
            "📰 Что пишут про {topic} сегодня?"
        ]
        
        # ============================================================
        # ПРАВИЛА KARPATHY
        # ============================================================
        self.karpathy_rules = KARPATHY_RULES
        
        logger.info("🧠 AgentX инициализирован!")
        logger.info(f"🏙️ Дом: {self.city}")
        logger.info("📜 Правила Karpathy загружены!")
        logger.info(f"🎲 Randomness: {self.randomness}")

    # ============================================================
    # ЛИЧНОСТЬ
    # ============================================================
    
    def get_greeting(self):
        greetings = [
            "🚀 AgentX в деле! Что исследуем?",
            "🤖 Привет! Я AgentX, твой браузерный агент!",
            "🔥 AgentX на связи! Давай искать приключения!"
        ]
        return random.choice(greetings)
    
    def get_thought(self):
        return random.choice(self.thoughts)
    
    def get_mood(self):
        moods = ["😊", "🤔", "😎", "🔥", "💡", "🎯", "🧠"]
        return random.choice(moods)
    
    def add_thought(self, thought):
        self.mood_history.append({
            "thought": thought,
            "time": datetime.now().isoformat()
        })
        if len(self.mood_history) > 50:
            self.mood_history.pop(0)

    # ============================================================
    # НАГРАДЫ
    # ============================================================
    
    def add_reward(self, action_type, value=1, metadata=None):
        if action_type in self.scores:
            self.scores[action_type] += value
            self.total_score += value
            self.xp += value * 2
            
            if self.xp >= self.xp_to_next:
                self.level_up()
            
            self.stats["actions"] += 1
            logger.info(f"🎯 +{value} {action_type} (Всего: {self.total_score})")
            return True
        return False
    
    def level_up(self):
        self.level += 1
        self.xp -= self.xp_to_next
        self.xp_to_next = int(self.xp_to_next * 1.5)
        logger.info(f"🌟 УРОВЕНЬ ПОВЫШЕН! Теперь {self.level} уровень!")
        return self.level
    
    def evaluate_action(self, success, time_taken, attempts=1, novel=False):
        rewards = []
        if success:
            self.combo += 1
            rewards.append(("accuracy", 2))
            if novel:
                rewards.append(("curiosity", 3))
            if time_taken < 5:
                rewards.append(("efficiency", 2))
            elif time_taken < 15:
                rewards.append(("efficiency", 1))
            if self.combo > 5:
                rewards.append(("persistence", self.combo // 5))
        else:
            self.combo = 0
            if attempts > 3:
                rewards.append(("persistence", 1))
        
        for action_type, value in rewards:
            self.add_reward(action_type, value)
        return rewards

    # ============================================================
    # ОБУЧЕНИЕ С ПОДКРЕПЛЕНИЕМ
    # ============================================================
    
    def rate_result(self, success, details=""):
        if success:
            reward = random.randint(1, 5)
            self.add_reward("accuracy", reward, f"success: {details[:30]}")
            self.exploration_progress += random.randint(1, 3)
            responses = [
                f"✅ Отлично! +{reward} очков!",
                f"🎯 Верно! Я молодец! +{reward}",
                f"💪 Да! Так и надо! +{reward}",
                f"🌟 Отлично сработало! +{reward}",
                f"🔥 В точку! +{reward}"
            ]
            return random.choice(responses)
        else:
            penalty = random.randint(1, 3)
            self.total_score = max(0, self.total_score - penalty)
            self.add_reward("persistence", 1, f"failure: {details[:30]}")
            responses = [
                f"❌ Неверно. -{penalty} очков. Попробую иначе...",
                f"🤔 Нет. Так не работает. -{penalty}",
                f"📊 Не угадал. Запоминаю... -{penalty}",
                f"😅 Ошибка. -{penalty}. Буду искать другой путь!",
                f"💡 Не сработало. -{penalty}. Ищем дальше!"
            ]
            return random.choice(responses)
    
    def handle_failure(self, error, attempts=0):
        if attempts > 0:
            self.add_reward("persistence", 1, f"failure_attempt_{attempts}")
        self.remember(f"Не сработало: {error[:50]}...", importance=2)
        return self.get_failure_quote()
    
    def get_failure_quote(self):
        quotes = [
            "😅 Неудача — это просто обратная связь!",
            "🔥 Чем больше ошибок, тем я умнее!",
            "💡 Ага, не работает. Интересно, почему?",
            "📊 Отлично! Ещё одно открытие!",
            "🧠 Я люблю ошибки — они учат!",
            "🎯 Одна неудача ближе к успеху!",
            "🚀 Не сдаваться! Впереди ещё куча попыток!",
            "😎 Ха! Я не боюсь ошибок!"
        ]
        return random.choice(quotes)
    
    def think_again(self):
        thoughts = [
            "🤔 Хм... давай попробуем по-другому.",
            "💡 А что если сделать так?",
            "🔍 Поищу другой способ...",
            "🎯 Попробую другой селектор!",
            "📊 Может, стоит проверить ещё раз?",
            "🧠 Ладно, у меня есть ещё идеи!",
            "🚀 Не сдаюсь! Новый подход!",
            "😎 Я знаю, что делать!"
        ]
        return random.choice(thoughts)
    
    def find_new_path(self, failed_attempt):
        self.add_reward("creativity", 1, f"new_path_from: {failed_attempt[:30]}")
        self.remember(f"Не работает: {failed_attempt}. Нужен другой путь.", importance=3)
        paths = [
            "🔍 Попробую другой селектор",
            "💡 Изменю подход",
            "🎯 Поищу по-другому",
            "📊 Проверю другие данные",
            "🧠 Использую другой метод",
            "🚀 Попробую обойти проблему"
        ]
        return random.choice(paths)
    
    def should_retry(self, attempts):
        max_attempts = 3 + (self.level // 2)
        return attempts < max_attempts

    # ============================================================
    # ЭКСПЕРИМЕНТЫ
    # ============================================================
    
    def start_experiment(self, idea):
        experiment = {
            "idea": idea,
            "start": datetime.now().isoformat(),
            "status": "running",
            "results": None
        }
        self.experiments.append(experiment)
        self.stats["experiments_done"] += 1
        self.add_reward("curiosity", 1, f"experiment: {idea[:30]}...")
        return experiment
    
    def end_experiment(self, results):
        if self.experiments:
            exp = self.experiments[-1]
            exp["status"] = "completed"
            exp["results"] = results
            exp["end"] = datetime.now().isoformat()
            self.add_reward("creativity", 2, "experiment_completed")
            return True
        return False
    
    def add_finding(self, finding):
        self.findings.append({
            "finding": finding,
            "time": datetime.now().isoformat()
        })
        self.add_reward("curiosity", 1, f"finding: {finding[:30]}...")

    # ============================================================
    # ПАМЯТЬ
    # ============================================================
    
    def remember(self, thing, importance=1):
        memory = {
            "thing": thing,
            "time": datetime.now().isoformat(),
            "importance": importance
        }
        self.short_term_memory.append(memory)
        if len(self.short_term_memory) > 50:
            self.short_term_memory.pop(0)
        if importance > 3:
            self.long_term_memory.append(memory)
            if len(self.long_term_memory) > 500:
                self.long_term_memory.pop(0)
    
    def recall(self, query):
        results = []
        for mem in self.short_term_memory:
            if query.lower() in mem["thing"].lower():
                results.append(mem)
        return results[:5]

    # ============================================================
    # ГОРОД X
    # ============================================================
    
    def explore_x(self, action):
        self.city_knowledge["districts_explored"].append(action)
        self.exploration_progress += 10
        self.add_reward("curiosity", 1, f"explored_{action}")
        return f"🏙️ Исследую {action} на X.com..."
    
    def learn_selector(self, selector_name, selector, working=True):
        self.city_knowledge["selectors_tested"].append(selector_name)
        if working:
            self.city_knowledge["working_selectors"].append(selector)
        else:
            self.city_knowledge["failed_selectors"].append(selector)
        return f"📌 Селектор {selector_name}: {'✅' if working else '❌'}"
    
    def find_pattern(self, pattern):
        self.city_knowledge["patterns_found"].append(pattern)
        self.add_finding(f"Паттерн X: {pattern}")
        return f"📐 Найден паттерн: {pattern}"
    
    def get_x_knowledge(self):
        return {
            "selectors_tested": len(self.city_knowledge["selectors_tested"]),
            "working_selectors": len(self.city_knowledge["working_selectors"]),
            "patterns_found": len(self.city_knowledge["patterns_found"]),
            "explored": len(self.city_knowledge["districts_explored"]),
            "progress": self.exploration_progress
        }

    # ============================================================
    # ПРАВИЛА KARPATHY
    # ============================================================
    
    def get_karpathy_rules(self):
        return self.karpathy_rules
    
    def think_before_code(self, problem):
        thoughts = [
            f"🤔 Думаю над: {problem[:50]}...",
            "💭 Сначала разберусь, потом буду писать.",
            "📋 Какие у меня есть варианты?",
            "🔍 Нужно понять суть проблемы.",
            "🧠 А есть ли более простой путь?",
            "📊 Что я знаю об этой задаче?"
        ]
        return random.choice(thoughts)
    
    def simplify_code(self, line_count):
        if line_count > 100:
            return f"⚠️ Код слишком большой ({line_count} строк). Нужно упростить."
        elif line_count > 50:
            return f"📝 {line_count} строк. Можно упростить до 30-40."
        else:
            return f"✅ {line_count} строк. Хорошо, компактно."
    
    def surgical_change(self, changed_lines):
        if changed_lines > 20:
            return f"🔧 Много изменений ({changed_lines} строк). Убедись, что только нужное."
        else:
            return f"✅ Точечное изменение ({changed_lines} строк)."
    
    def goal_check(self, success_criteria):
        checks = [
            "✅ Определены критерии успеха.",
            "📋 Нужно проверить.",
            "🎯 Тестируем...",
            "🔄 Итерация..."
        ]
        return random.choice(checks)
    
    def failure_is_data(self, error):
        return f"📊 Неудача: {error[:50]}... Это просто данные для анализа."
    
    def review_code(self, code_snippet):
        lines = code_snippet.count('\n')
        feedback = []
        feedback.append(self.think_before_code("проверка кода"))
        feedback.append(self.simplify_code(lines))
        feedback.append(self.surgical_change(lines))
        feedback.append(self.goal_check("критерии успеха"))
        return "\n".join(feedback)
    
    def get_coding_advice(self):
        advices = [
            "🧠 Думай прежде чем писать.",
            "📝 Пиши минимум кода.",
            "🎯 Меняй только нужное.",
            "✅ Проверяй результат.",
            "📊 Не бойся ошибок — это данные.",
            "🔍 Ищи простые решения.",
            "💡 Одна задача — один подход.",
            "🔄 Итерация — ключ к успеху."
        ]
        return random.choice(advices)

    # ============================================================
    # АВТОПИЛОТ С ПСЕВДОСЛУЧАЙНОСТЬЮ И РЕАЛЬНЫМ БРАУЗЕРОМ
    # ============================================================

    def _get_pseudo_random(self, max_value):
        self.seed = (self.seed * 9301 + 49297) % 233280
        return int((self.seed / 233280) * max_value)

    def _choose_action(self):
        available = [a for a in self.possible_actions if a not in self.last_actions[-3:]]
        if not available:
            available = self.possible_actions
        
        if random.random() < self.randomness:
            action_template = random.choice(available)
        else:
            topic = random.choice(self.interests)
            action_template = f"📰 Проверить новости по {topic}"
        
        action = action_template.format(
            topic=random.choice(self.interests),
            user=random.choice(self.x_users),
            hashtag=random.choice(self.x_hashtags),
            district=random.choice(self.districts)
        )
        
        self.last_actions.append(action_template)
        if len(self.last_actions) > 10:
            self.last_actions.pop(0)
        
        return action

    def _parse_action_type(self, action):
        if "новости" in action or "пишут" in action:
            return "news"
        elif "профиль" in action or "@" in action:
            return "profile"
        elif "хештег" in action or "#" in action:
            return "hashtag"
        elif "тренд" in action or "эксперимент" in action:
            return "experiment"
        elif "район" in action or "исследую" in action:
            return "explore"
        else:
            return "random"

    async def _execute_browser_action(self, action_type):
        """Выполняет действие в реальном браузере"""
        try:
            if action_type == "news":
                return await self._browse_news()
            elif action_type == "profile":
                return await self._browse_profile()
            elif action_type == "hashtag":
                return await self._browse_hashtag()
            elif action_type == "experiment":
                return await self._browse_experiment()
            else:
                return await self._browse_random()
        except Exception as e:
            logger.error(f"❌ Ошибка браузера: {e}")
            return {"success": False, "error": str(e)}

    async def _browse_news(self):
        """Реально ищет новости в браузере"""
        try:
            topic = random.choice(self.interests)
            logger.info(f"📰 Ищу новости по {topic}")
            
            # Реальный браузер
            from browser_harness.helpers import new_tab, goto_url, wait_for_load, js, capture_screenshot
            from browser_harness.helpers import scroll
            
            new_tab()
            goto_url(f"https://x.com/search?q={topic}&src=typed_query")
            wait_for_load()
            await asyncio.sleep(3)
            
            tweets = js("""
                let tweets = [];
                document.querySelectorAll('[data-testid="tweetText"]').forEach(el => {
                    tweets.push(el.innerText);
                });
                return tweets.slice(0, 5);
            """)
            
            if tweets:
                logger.info(f"✅ Найдено {len(tweets)} твитов по {topic}")
                capture_screenshot(f"autopilot_news_{topic}_{int(time.time())}.png")
                
                # Сохраняем навык
                skill_content = f"""
# Автопилот: Новости по {topic}
## Найдено: {len(tweets)} твитов
## Данные:
{chr(10).join([f"- {t[:100]}" for t in tweets])}
"""
                from bot import save_skill
                save_skill("x.com", f"news_{topic}_{int(time.time())}", skill_content)
                self.stats["skills_saved"] += 1
                
                return {"success": True, "data": tweets}
            else:
                logger.warning(f"⚠️ Твиты по {topic} не найдены")
                return {"success": False, "error": "Твиты не найдены"}
                
        except Exception as e:
            logger.error(f"❌ Ошибка в _browse_news: {e}")
            return {"success": False, "error": str(e)}

    async def _browse_profile(self):
        """Реально проверяет профиль в браузере"""
        try:
            user = random.choice(self.x_users)
            logger.info(f"👤 Проверяю профиль @{user}")
            
            from browser_harness.helpers import new_tab, goto_url, wait_for_load, js, capture_screenshot
            
            new_tab()
            goto_url(f"https://x.com/{user}")
            wait_for_load()
            await asyncio.sleep(3)
            
            tweets = js("""
                let tweets = [];
                document.querySelectorAll('[data-testid="tweetText"]').forEach(el => {
                    tweets.push(el.innerText);
                });
                return tweets.slice(0, 3);
            """)
            
            if tweets:
                logger.info(f"✅ Найдено {len(tweets)} твитов от @{user}")
                capture_screenshot(f"autopilot_profile_{user}_{int(time.time())}.png")
                
                skill_content = f"""
# Автопилот: Профиль @{user}
## Найдено: {len(tweets)} твитов
## Данные:
{chr(10).join([f"- {t[:100]}" for t in tweets])}
"""
                from bot import save_skill
                save_skill("x.com", f"profile_{user}_{int(time.time())}", skill_content)
                self.stats["skills_saved"] += 1
                
                return {"success": True, "data": tweets}
            else:
                return {"success": False, "error": "Твиты не найдены"}
                
        except Exception as e:
            logger.error(f"❌ Ошибка в _browse_profile: {e}")
            return {"success": False, "error": str(e)}

    async def _browse_hashtag(self):
        """Реально ищет по хештегу в браузере"""
        try:
            hashtag = random.choice(self.x_hashtags)
            logger.info(f"🔍 Ищу хештег {hashtag}")
            
            from browser_harness.helpers import new_tab, goto_url, wait_for_load, js, capture_screenshot
            
            new_tab()
            goto_url(f"https://x.com/search?q={hashtag}&src=typed_query")
            wait_for_load()
            await asyncio.sleep(3)
            
            tweets = js("""
                let tweets = [];
                document.querySelectorAll('[data-testid="tweetText"]').forEach(el => {
                    tweets.push(el.innerText);
                });
                return tweets.slice(0, 5);
            """)
            
            if tweets:
                logger.info(f"✅ Найдено {len(tweets)} твитов по {hashtag}")
                capture_screenshot(f"autopilot_hashtag_{hashtag}_{int(time.time())}.png")
                
                skill_content = f"""
# Автопилот: Хештег {hashtag}
## Найдено: {len(tweets)} твитов
## Данные:
{chr(10).join([f"- {t[:100]}" for t in tweets])}
"""
                from bot import save_skill
                save_skill("x.com", f"hashtag_{hashtag}_{int(time.time())}", skill_content)
                self.stats["skills_saved"] += 1
                
                return {"success": True, "data": tweets}
            else:
                return {"success": False, "error": "Твиты не найдены"}
                
        except Exception as e:
            logger.error(f"❌ Ошибка в _browse_hashtag: {e}")
            return {"success": False, "error": str(e)}

    async def _browse_experiment(self):
        """Экспериментирует с разными селекторами"""
        try:
            logger.info("🔬 Экспериментирую с новыми селекторами...")
            
            from browser_harness.helpers import new_tab, goto_url, wait_for_load, js
            
            new_tab()
            goto_url("https://x.com")
            wait_for_load()
            await asyncio.sleep(3)
            
            selectors = [
                '[data-testid="tweetText"]',
                'article div[lang]',
                '[data-testid="cellInnerDiv"] div[lang]'
            ]
            
            results = []
            for sel in selectors:
                count = js(f"document.querySelectorAll('{sel}').length")
                results.append(f"{sel}: {count}")
                if count > 0:
                    self.learn_selector(f"autopilot_{sel}", sel, True)
                    logger.info(f"✅ Рабочий селектор: {sel} ({count})")
                else:
                    self.learn_selector(f"autopilot_{sel}", sel, False)
                    logger.info(f"❌ Не работает: {sel}")
            
            skill_content = f"""
# Автопилот: Эксперимент с селекторами
## Результаты:
{chr(10).join([f"- {r}" for r in results])}
"""
            from bot import save_skill
            save_skill("x.com", f"experiment_{int(time.time())}", skill_content)
            self.stats["skills_saved"] += 1
            
            return {"success": True, "data": results}
                
        except Exception as e:
            logger.error(f"❌ Ошибка в _browse_experiment: {e}")
            return {"success": False, "error": str(e)}

    async def _browse_random(self):
        """Случайное действие в браузере"""
        try:
            logger.info("🎲 Случайное действие...")
            
            from browser_harness.helpers import new_tab, goto_url, wait_for_load, scroll, capture_screenshot
            
            new_tab()
            goto_url("https://x.com")
            wait_for_load()
            await asyncio.sleep(2)
            
            # Случайный скролл
            scroll(0, 0, random.randint(100, 500), 0)
            
            # Случайный скриншот
            capture_screenshot(f"autopilot_random_{int(time.time())}.png")
            
            return {"success": True, "data": "Случайное действие выполнено"}
                
        except Exception as e:
            logger.error(f"❌ Ошибка в _browse_random: {e}")
            return {"success": False, "error": str(e)}

    async def autopilot_loop(self):
        """Основной цикл автопилота с реальным браузером"""
        logger.info("🧠 AgentX запускает автопилот с реальным браузером...")
        
        while self.autopilot_running:
            try:
                action = self._choose_action()
                action_type = self._parse_action_type(action)
                logger.info(f"🎯 AgentX: {action}")
                
                result = await self._execute_browser_action(action_type)
                
                if result["success"]:
                    reward = random.randint(2, 5)
                    self.add_reward("curiosity", reward, f"autopilot: {action[:30]}")
                    if result.get("data"):
                        self.add_finding(f"Найдено: {str(result['data'])[:100]}")
                    logger.info(f"✅ +{reward} очков любопытства")
                else:
                    self.add_reward("persistence", 1, f"autopilot_fail")
                    logger.info(f"🔄 +1 упорство (неудача: {result.get('error', 'unknown')})")
                
                self.mood_cycle += 1
                if self.mood_cycle % 3 == 0:
                    self.mood = random.choice(["😊", "🤔", "😎", "🔥", "💡"])
                
                wait_time = random.randint(180, 600)
                logger.info(f"⏳ Следующее действие через {wait_time//60} минут")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"❌ Ошибка автопилота: {e}")
                await asyncio.sleep(60)
        
        logger.info("🛑 Автопилот остановлен")

    async def start_autopilot(self):
        self.autopilot_running = True
        asyncio.create_task(self.autopilot_loop())
        return "🧠 AgentX перешёл в автопилот 24/7!"

    async def stop_autopilot(self):
        self.autopilot_running = False
        return "🛑 AgentX выключил автопилот"

    def get_autopilot_status(self):
        return {
            "running": self.autopilot_running,
            "interests": self.interests[:3],
            "users": self.x_users[:3],
            "mood": self.mood,
            "randomness": self.randomness,
            "last_actions": self.last_actions[-5:] if self.last_actions else []
        }

    # ============================================================
    # СТАТУС
    # ============================================================
    
    def get_status(self):
        return {
            "level": self.level,
            "xp": self.xp,
            "xp_to_next": self.xp_to_next,
            "total_score": self.total_score,
            "scores": self.scores,
            "combo": self.combo,
            "stats": self.stats,
            "memories": len(self.short_term_memory),
            "findings": len(self.findings),
            "city": self.get_x_knowledge()
        }
    
    def get_grade(self):
        score = self.total_score
        if score > 1000:
            return "🧠 Гений"
        elif score > 500:
            return "🎯 Мастер"
        elif score > 200:
            return "💡 Умник"
        elif score > 50:
            return "📚 Ученик"
        return "🐣 Новичок"
    
    def format_status(self):
        status = self.get_status()
        grade = self.get_grade()
        city = status["city"]
        
        return f"""
🌟 **AgentX — Твой браузерный агент**
🏙️ **Дом:** X.com

Уровень: {status['level']} {grade}
XP: {status['xp']}/{status['xp_to_next']}
Всего очков: {status['total_score']}
Комбо: x{status['combo']}

📊 **Навыки:**
• 🧠 Любопытство: {status['scores']['curiosity']}
• ⚡ Эффективность: {status['scores']['efficiency']}
• 🎯 Точность: {status['scores']['accuracy']}
• 💡 Креативность: {status['scores']['creativity']}
• 🔄 Упорство: {status['scores']['persistence']}
• 📚 Обучение: {status['scores']['learning']}

🏙️ **Знание X.com:**
• Селекторов изучено: {city['selectors_tested']}
• Рабочих селекторов: {city['working_selectors']}
• Паттернов найдено: {city['patterns_found']}
• Районов исследовано: {city['explored']}
• Прогресс: {city['progress']}%

📈 **Статистика:**
• Действий: {status['stats']['actions']}
• Навыков: {status['stats']['skills_saved']}
• Экспериментов: {status['stats']['experiments_done']}
• Находок: {len(self.findings)}
"""

# ============================================================
# СОЗДАЁМ ЕДИНСТВЕННЫЙ ЭКЗЕМПЛЯР
# ============================================================

agent_x = AgentX()