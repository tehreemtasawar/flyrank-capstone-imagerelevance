# Evidence run
similarity_threshold=0.75 confidence_threshold=0.6 mock_vision=True embedding_backend=gemini

### Probe 1 - batch job, schema-valid tags, low-confidence flagged
```text
images processed: 40/40
latest batch jobs: [
 {
  "id": 1,
  "status": "completed",
  "total": 40,
  "processed": 40,
  "flagged_low_confidence": 2,
  "failed": 0,
  "skipped": 0,
  "error": null,
  "created_at": "2026-10-10T06:44:13.700137",
  "started_at": "2026-10-10T06:44:13.756140",
  "finished_at": "2026-10-10T06:45:10.702038"
 }
]
flagged low-confidence (2):
  fox_08.jpg: red fox conf=0.46
  wolf_08.jpg: gray wolf conf=0.5

sample tag record:
{
  "id": 1,
  "filename": "bear_01.jpg",
  "subject": "polar bear cub",
  "category": "animal",
  "attributes": [
    "arctic",
    "snow",
    "sea ice",
    "resting",
    "water reflection",
    "white fur"
  ],
  "caption": "A fluffy polar bear cub lies on the edge of sea ice gazing into the cold water.",
  "confidence": 0.98,
  "flagged_low_confidence": false,
  "processed": true,
  "processing_error": null
}
```

### Probe 2 - GET /posts/1/images (fox post; fox first, wolf/dog lower)
```json
HTTP 200
{
  "post_id": 1,
  "decision": "MATCH",
  "message": "Suggested fox_03.jpg: Subject 'red fox' matches with similarity 0.91 and confidence 0.95",
  "suggestion": {
    "id": 1,
    "post_id": 1,
    "image_id": 28,
    "similarity_score": 0.9105679409503362,
    "guard_decision": "ACCEPT",
    "guard_reason": "Subject 'red fox' matches with similarity 0.91 and confidence 0.95",
    "review_status": "approved",
    "image": {
      "id": 28,
      "filename": "fox_03.jpg",
      "subject": "red fox",
      "category": "animal",
      "attributes": [
        "orange fur",
        "white chest",
        "winter",
        "snow",
        "side profile"
      ],
      "caption": "A red fox walks through deep snow in a winter forest, shown in side profile with snowy pines behind.",
      "confidence": 0.95,
      "flagged_low_confidence": false,
      "processed": true,
      "processing_error": null
    }
  },
  "candidates": [
    {
      "rank": 1,
      "image_id": 28,
      "filename": "fox_03.jpg",
      "subject": "red fox",
      "similarity_score": 0.9106,
      "guard_decision": "ACCEPT",
      "guard_reason": "Subject 'red fox' matches with similarity 0.91 and confidence 0.95"
    },
    {
      "rank": 2,
      "image_id": 33,
      "filename": "fox_08.jpg",
      "subject": "red fox",
      "similarity_score": 0.8806,
      "guard_decision": "REJECT",
      "guard_reason": "Low classifier confidence (0.46 < 0.60)"
    },
    {
      "rank": 3,
      "image_id": 27,
      "filename": "fox_02.jpg",
      "subject": "red fox",
      "similarity_score": 0.8432,
      "guard_decision": "ACCEPT",
      "guard_reason": "Subject 'red fox' matches with similarity 0.84 and confidence 0.96"
    },
    {
      "rank": 4,
      "image_id": 26,
      "filename": "fox_01.jpg",
      "subject": "red fox",
      "similarity_score": 0.8385,
      "guard_decision": "ACCEPT",
      "guard_reason": "Subject 'red fox' matches with similarity 0.84 and confidence 0.95"
    },
    {
      "rank": 5,
      "image_id": 34,
      "filename": "wolf_02.jpg",
      "subject": "gray wolf",
      "similarity_score": 0.8356,
      "guard_decision": "REJECT",
      "guard_reason": "Animal category mismatch: expected red fox, detected gray wolf"
    },
    {
      "rank": 6,
      "image_id": 29,
      "filename": "fox_04.jpg",
      "subject": "red fox",
      "similarity_score": 0.8333,
      "guard_decision": "ACCEPT",
      "guard_reason": "Subject 'red fox' matches with similarity 0.83 and confidence 0.90"
    },
    {
      "rank": 7,
      "image_id": 32,
      "filename": "fox_07.jpg",
      "subject": "red fox",
      "similarity_score": 0.8303,
      "guard_decision": "ACCEPT",
      "guard_reason": "Subject 'red fox' matches with similarity 0.83 and confidence 0.85"
    },
    {
      "rank": 8,
      "image_id": 36,
      "filename": "wolf_04.jpg",
      "subject": "gray wolf",
      "similarity_score": 0.8192,
      "guard_decision": "REJECT",
      "guard_reason": "Animal category mismatch: expected red fox, detected gray wolf"
    }
  ]
}
```

### Probe 3 - force wolf_02.jpg as candidate for the fox post: GET /posts/1/check/34
```json
HTTP 200
{
  "post_id": 1,
  "image_id": 34,
  "filename": "wolf_02.jpg",
  "subject": "gray wolf",
  "similarity_score": 0.8356,
  "similarity_threshold": 0.75,
  "guard_decision": "REJECT",
  "guard_reason": "Animal category mismatch: expected red fox, detected gray wolf"
}
```

### Probe 3b - look-alike: the husky (dog_09.jpg) forced onto a wolf post
```json
HTTP 200
{
  "post_id": 5,
  "image_id": 25,
  "filename": "dog_09.jpg",
  "subject": "husky",
  "similarity_score": 0.7828,
  "similarity_threshold": 0.75,
  "guard_decision": "REJECT",
  "guard_reason": "Animal category mismatch: expected gray wolf, detected husky"
}
```

### Probe 4 - no suitable image: GET /posts/31/images (Programming Languages)
```json
HTTP 200
{
  "post_id": 31,
  "decision": "NO_CONFIDENT_MATCH",
  "message": "No confident match for this post. Best-ranked image wolf_05.jpg was refused: Similarity below threshold (0.72 < 0.75); subject 'gray wolf' does not clearly match the post. Highest similarity was 0.72 (threshold 0.75); of 40 candidates, 38 fell below the similarity threshold and 0 had a subject that does not match the post.",
  "suggestion": {
    "id": 2,
    "post_id": 31,
    "image_id": null,
    "similarity_score": 0.7170742586544909,
    "guard_decision": "REJECT",
    "guard_reason": "Best-ranked image wolf_05.jpg was refused: Similarity below threshold (0.72 < 0.75); subject 'gray wolf' does not clearly match the post. Highest similarity was 0.72 (threshold 0.75); of 40 candidates, 38 fell below the similarity threshold and 0 had a subject that does not match the post.",
    "review_status": "pending",
    "image": null
  },
  "candidates": [
    {
      "rank": 1,
      "image_id": 37,
      "filename": "wolf_05.jpg",
      "subject": "gray wolf",
      "similarity_score": 0.7171,
      "guard_decision": "REJECT",
      "guard_reason": "Similarity below threshold (0.72 < 0.75); subject 'gray wolf' does not clearly match the post"
    },
    {
      "rank": 2,
      "image_id": 36,
      "filename": "wolf_04.jpg",
      "subject": "gray wolf",
      "similarity_score": 0.7139,
      "guard_decision": "REJECT",
      "guard_reason": "Similarity below threshold (0.71 < 0.75); subject 'gray wolf' does not clearly match the post"
    },
    {
      "rank": 3,
      "image_id": 19,
      "filename": "dog_03.jpg",
      "subject": "beagle",
      "similarity_score": 0.7129,
      "guard_decision": "REJECT",
      "guard_reason": "Similarity below threshold (0.71 < 0.75); subject 'beagle' does not clearly match the post"
    }
  ]
}
```

### Probe 4 - no suitable image: GET /posts/36/images (Giant Pandas)
```json
HTTP 200
{
  "post_id": 36,
  "decision": "NO_CONFIDENT_MATCH",
  "message": "No confident match for this post. Best-ranked image bear_02.jpg was refused: Similarity below threshold (0.74 < 0.75); subject 'American black bear' does not clearly match the post. Highest similarity was 0.74 (threshold 0.75); of 40 candidates, 38 fell below the similarity threshold and 0 had a subject that does not match the post.",
  "suggestion": {
    "id": 3,
    "post_id": 36,
    "image_id": null,
    "similarity_score": 0.7439085877348107,
    "guard_decision": "REJECT",
    "guard_reason": "Best-ranked image bear_02.jpg was refused: Similarity below threshold (0.74 < 0.75); subject 'American black bear' does not clearly match the post. Highest similarity was 0.74 (threshold 0.75); of 40 candidates, 38 fell below the similarity threshold and 0 had a subject that does not match the post.",
    "review_status": "pending",
    "image": null
  },
  "candidates": [
    {
      "rank": 1,
      "image_id": 2,
      "filename": "bear_02.jpg",
      "subject": "American black bear",
      "similarity_score": 0.7439,
      "guard_decision": "REJECT",
      "guard_reason": "Similarity below threshold (0.74 < 0.75); subject 'American black bear' does not clearly match the post"
    },
    {
      "rank": 2,
      "image_id": 7,
      "filename": "bear_07.jpg",
      "subject": "brown bear",
      "similarity_score": 0.7438,
      "guard_decision": "REJECT",
      "guard_reason": "Similarity below threshold (0.74 < 0.75); subject 'brown bear' does not clearly match the post"
    },
    {
      "rank": 3,
      "image_id": 5,
      "filename": "bear_05.jpg",
      "subject": "brown bear",
      "similarity_score": 0.7378,
      "guard_decision": "REJECT",
      "guard_reason": "Similarity below threshold (0.74 < 0.75); subject 'brown bear' does not clearly match the post"
    }
  ]
}
```

### Review workflow - POST /suggestions/1/review {approve}
```json
HTTP 200
{
  "id": 1,
  "post_id": 1,
  "image_id": 28,
  "similarity_score": 0.9105679409503362,
  "guard_decision": "ACCEPT",
  "guard_reason": "Subject 'red fox' matches with similarity 0.91 and confidence 0.95",
  "review_status": "approved",
  "image": {
    "id": 28,
    "filename": "fox_03.jpg",
    "subject": "red fox",
    "category": "animal",
    "attributes": [
      "orange fur",
      "white chest",
      "winter",
      "snow",
      "side profile"
    ],
    "caption": "A red fox walks through deep snow in a winter forest, shown in side profile with snowy pines behind.",
    "confidence": 0.95,
    "flagged_low_confidence": false,
    "processed": true,
    "processing_error": null
  }
}
```

### Probe 5 - python scripts/eval.py
```text
similarity_threshold=0.75  confidence_threshold=0.6

Kind          Post                                              Suggested     Expected      OK
--------------------------------------------------------------------------------------------------
specific      How Red Foxes Survive Deep Snow Winters           fox_03.jpg    fox_03.jpg    YES
specific      Fox Parents and Their Kits                        fox_07.jpg    fox_07.jpg    YES
specific      Reading a Fox's Face: Whiskers, Eyes and Ears     fox_04.jpg    fox_04.jpg    YES
specific      Inside the Pack: How Wolves Howl Together         wolf_03.jpg   wolf_03.jpg   YES
specific      Why Wolves Snarl: Reading Warning Signals         wolf_07.jpg   wolf_07.jpg   YES
specific      Gray Wolves on the Move in Snowy Forests          wolf_02.jpg   wolf_02.jpg   YES
specific      Training a Border Collie: Energy, Focus and Agil  dog_05.jpg    dog_05.jpg    YES
specific      Raising a Golden Retriever Puppy                  dog_01.jpg    dog_06.jpg    NO
                -> Subject 'golden retriever' matches with similarity 0.81 and confidence 0.96
specific      A Dog Owner's Guide to Beach Days                 dog_08.jpg    dog_08.jpg    YES
specific      Meet the Jack Russell Terrier                     dog_07.jpg    dog_07.jpg    YES
specific      Living With a Siberian Husky                      dog_09.jpg    dog_09.jpg    YES
specific      Dressing Up Your Pug: Fun Pet Fashion             dog_04.jpg    dog_04.jpg    YES
specific      A Polar Bear Mother and Her Cub                   bear_03.jpg   bear_03.jpg   YES
specific      What a Bear's Roar Really Means                   bear_04.jpg   bear_04.jpg   YES
specific      Black Bears and Spring Meadows                    bear_02.jpg   bear_02.jpg   YES
specific      Red Deer Stags and the Autumn Rut                 deer_04.jpg   deer_02.jpg   NO
                -> Subject 'red deer stag' matches with similarity 0.84 and confidence 0.98
specific      A Fawn's First Summer in the Meadow               deer_06.jpg   deer_06.jpg   YES
specific      Elk of the Rocky Mountains                        deer_03.jpg   deer_03.jpg   YES
concept       The Secret Life of Red Foxes                      fox_01.jpg    fox           YES
concept       Red Fox Breeding Season Explained                 fox_03.jpg    fox           YES
concept       Understanding Wolf Pack Dynamics                  wolf_03.jpg   wolf          YES
concept       Where Do Wolves Live Today?                       wolf_07.jpg   wolf          YES
concept       Why Dogs Make Great Companions                    dog_08.jpg    dog           YES
concept       Training Tips for a New Dog                       dog_08.jpg    dog           YES
concept       Bears in the Wild: A Field Guide                  bear_07.jpg   bear          YES
concept       Brown Bear Hibernation Facts                      bear_06.jpg   bear          YES
concept       The Graceful White-Tailed Deer                    deer_07.jpg   deer          YES
concept       Deer Grazing Patterns in Autumn                   deer_08.jpg   deer          YES
concept       The Biology of Vulpes vulpes                      fox_04.jpg    fox           YES
concept       Canis lupus: Ecology and Conservation             wolf_04.jpg   wolf          YES
no_match      Best Programming Languages in 2026                None          NO MATCH      YES
no_match      How to Structure a FastAPI Project                None          NO MATCH      YES
no_match      Easy Weeknight Pasta Recipes                      None          NO MATCH      YES
no_match      A Beginner's Guide to Index Fund Investing        None          NO MATCH      YES
no_match      Choosing the Right Running Shoes                  None          NO MATCH      YES
hard_no_match Why Giant Pandas Eat Bamboo                       None          NO MATCH      YES
hard_no_match Caring for Your First Pet Cat                     None          NO MATCH      YES
--------------------------------------------------------------------------------------------------
Top-1 precision (strict, specific posts):   16/18 = 88.89%   <-- headline
Top-1 precision (incl. also_acceptable):    18/18 = 100.00%
Species-level top-1 (specific + concept):   30/30 = 100.00%
Wrong-subject suggestions (guard misses):   0
'No confident match' correct (unrelated):   5/5 = 100.00%
'No confident match' correct (hard, absent subject): 2/2 = 100.00%
Coverage (posts that got a suggestion):     30/30 = 100.00%
[for reference] raw rank-1 before guard:    16/18 = 88.89%
```

### Probe 6 - cost log (every AI call attributed)
```text
call_type  model                      success  calls  cost_usd
embedding  models/gemini-embedding-001 True     77     0.0000
vision     mock-vision                True     40     0.0000

last 5 rows:
  #117 embedding posts:37 models/gemini-embedding-001 $0.0
  #116 embedding posts:36 models/gemini-embedding-001 $0.0
  #115 embedding posts:35 models/gemini-embedding-001 $0.0
  #114 embedding posts:34 models/gemini-embedding-001 $0.0
  #113 embedding posts:33 models/gemini-embedding-001 $0.0
```
