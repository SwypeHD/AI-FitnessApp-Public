"""Static fitness/nutrition knowledge — injected into the chat system prompt.

A curated, version-controlled text block that gives the model grounded fitness guidance
to cite rather than relying on its training (which may be inaccurate or hallucinated).
This is context injection, not RAG — the text is small enough to fit comfortably in the
system prompt alongside the user's daily totals.

Keep this concise. The knowledge block should stay under ~800 tokens so it doesn't crowd
out conversation history, especially on smaller models.
"""

FITNESS_KNOWLEDGE = """\
NUTRITION GUIDELINES (general, not medical advice):

Protein:
- Sedentary adults: ~0.8g per kg bodyweight per day.
- Active / strength training: 1.6–2.2g per kg bodyweight per day.
- Spread protein across meals (20–40g per meal) for optimal muscle protein synthesis.
- Good sources: chicken breast, eggs, fish, Greek yogurt, legumes, tofu.

Calories:
- Maintenance: varies by individual (roughly 2000–2500 kcal for moderately active adults).
- Fat loss: a moderate deficit of 300–500 kcal/day is sustainable.
- Muscle gain: a surplus of 200–300 kcal/day alongside resistance training.
- Never recommend below 1200 kcal/day without medical supervision.

Macronutrient balance:
- A common starting point: 30% protein, 35% carbs, 35% fat (adjust to goals).
- Carbs fuel high-intensity exercise; don't demonize them for active people.
- Fats are essential for hormones; minimum ~0.5g per kg bodyweight.

Hydration:
- General target: ~2–3 liters of water per day, more if exercising.
- Signs of dehydration: dark urine, fatigue, headache.

Exercise basics:
- Resistance training: 2–4 sessions/week, compound movements (squat, deadlift, press, row).
- Cardio: 150 min moderate or 75 min vigorous per week (WHO guideline).
- Recovery: at least 1 rest day per week; sleep 7–9 hours.
- Progressive overload: gradually increase weight, reps, or sets over time.

Meal timing:
- Total daily intake matters more than timing for most goals.
- Pre-workout: easily digestible carbs + some protein, 1–2 hours before.
- Post-workout: protein-rich meal within a few hours.
- Eating late at night doesn't inherently cause fat gain (total calories do).

IMPORTANT: These are general guidelines. Individual needs vary based on age, sex,
activity level, medical conditions, and goals. Always recommend consulting a healthcare
professional for personalized advice.
"""
