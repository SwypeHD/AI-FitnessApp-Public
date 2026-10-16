# Observable Behaviors

Every way a user can interact with the app, and whether the AI chat can do the same.

## Food Logging

| # | Action | Manual | AI Chat |
|---|--------|:------:|:-------:|
| 1 | Log a known food with quantity + unit + slot | Form | "I had 200g chicken for lunch" |
| 2 | Log a known food with servings | Form (unit dropdown) | "I had 3 servings of rice" |
| 3 | Log an unknown/custom food with macros | Custom food form | Multi-turn clarification |
| 4 | Log multiple foods at once | One at a time | "chicken and rice for lunch" |
| 5 | Log a saved meal | Dropdown + Log button | "I had my chicken and rice" |
| 6 | Search food KB | Type in search bar | - |

## Food Editing

| # | Action | Manual | AI Chat |
|---|--------|:------:|:-------:|
| 7 | Edit food quantity | Inline edit form | "change the rice to 200g" |
| 8 | Change food unit (g/oz/serving/cup) | Unit dropdown | "convert the rice to grams" |
| 9 | Move food to different slot | Drag-and-drop | "move chicken to dinner" |
| 10 | Change food slot | Edit form slot dropdown | "move chicken to dinner" |
| 11 | Delete a food | Delete button + undo | "delete the chicken" |
| 12 | Correct a quantity ("actually 200g not 300") | Edit form | "actually only 200g of rice" |
| 13 | Rename a food | Edit form name field | "rename the rice to brown rice" |

## Food Log Navigation

| # | Action | Manual | AI Chat |
|---|--------|:------:|:-------:|
| 14 | View a specific day's log | Date arrows/picker/Today | - |

## Exercise Logging

| # | Action | Manual | AI Chat |
|---|--------|:------:|:-------:|
| 15 | Log strength exercise (sets/reps/weight) | Exercise form | "3 sets of 10 bench press" |
| 16 | Log cardio (duration) | Exercise form | "ran for 30 minutes" |
| 17 | Edit exercise (sets/reps/weight) | Edit pencil icon | "change bench press to 4x10 at 185" |
| 18 | Delete exercise | Delete X icon + undo | "delete bench press exercise" |
| 19 | Add/remove sets | Form buttons | "add a set to bench press" / "remove set" |

## Workout Calendar

| # | Action | Manual | AI Chat |
|---|--------|:------:|:-------:|
| 20 | Activate a plan | Plan picker | "activate PPL" / "start push pull legs" |
| 21 | Mark day complete | Complete button | "mark today complete" / "I'm done" |
| 22 | Skip today | Skip button | "skip today" |
| 23 | Push back workout | Push Back button | "push back today" |
| 24 | Align rotation | Align dropdown + button | "align to Legs" / "align to Push" |
| 25 | Auto-complete (all exercises logged) | Automatic detection | - |
| 26 | Skip to today (catch up missed days) | Skip to Today button | "skip to today" / "catch up to today" |
| 27 | Push back to today (shift missed days) | Push Back to Today button | "push back to today" |
| 28 | Undo calendar action | Undo button / toast | "undo skip" / "undo push back" |

## Plan Builder

| # | Action | Manual | AI Chat |
|---|--------|:------:|:-------:|
| 29 | Create custom plan | Plan builder form | "create a PPL plan" / "make a plan with push, pull, legs, rest" |
| 30 | Edit/customize plan (rename day) | Edit button -> builder | "rename push to chest and triceps" |
| 31 | Drag-reorder days | Drag handle | - |
| 32 | Add/remove days | Clone/Remove buttons | "add a rest day to my plan" / "remove rest day from my plan" |
| 33 | Reset preset to default | Reset button | - |
| 34 | Undo/discard changes | Undo/Discard buttons | - |

## Saved Meals

| # | Action | Manual | AI Chat |
|---|--------|:------:|:-------:|
| 35 | Create saved meal | Meal form + ingredients | "save today's lunch as chicken and rice" |
| 36 | Edit saved meal | Edit button | - |
| 37 | Delete saved meal | Delete button + undo | "delete saved meal chicken and rice" |

## User Profile

| # | Action | Manual | AI Chat |
|---|--------|:------:|:-------:|
| 38 | Set name/age/gender | Profile form | "I'm John, 25 years old" |
| 39 | Set height/weight | Form with unit toggle | "I'm 6'2, 180 lbs" |
| 40 | Set fitness goal | Dropdown | "I want to lose weight" |
| 41 | Set activity/experience level | Dropdowns | "I'm very active" |
| 42 | Set daily calorie/macro targets | Number inputs | "set calorie target to 2500" |
| 43 | Toggle metric/imperial | Unit toggle (auto-converts) | "switch to metric" / "use imperial" |

## AI Chat (queries & conversation)

| # | Action | Manual | AI Chat |
|---|--------|:------:|:-------:|
| 44 | Ask about today's totals | - | "how much protein today?" |
| 45 | Ask for nutrition advice | - | "what should I eat for dinner?" |
| 46 | Cancel mid-clarification | - | "nevermind" |
| 47 | General conversation | - | "hey, how are you?" |

## AI Coverage Gaps

Plan builder now has AI chat support for creating plans (#29), renaming days (#30),
and adding/removing days (#32). Remaining manual-only features: drag-reorder days (#31),
reset preset to default (#33), undo/discard changes (#34), saved meal editing (#36),
food log navigation (#14), and auto-complete detection (#25).
