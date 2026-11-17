# the jobscraper
this is a jobscraping script that allows one to automatically apply to dozens of jobs simultaneously, but in an efficient ai-powered manner and allows you to write your own responses. 

## pipeline
### collection
1. collect websites with job listings 
2. filter jobs by the type or via keywords (deterministic)
  - should be able to search via keywords
  - should be both inclusive and exclusive (ie search for "internships" + "machine learning" + disclude "senior engineer" or etc)
3. collect job title, job type, field of industry, application link, and questions
### response 
4. upload resume
5. identify questions with ai
6. search a question database (such as a table) to see if the response has already been answered for a similar question (ie "why are you fit for this position?" in job type "internship" of job field "machine learning")
7. since this question would apply to this job, ai will tweak it (ie by replacing company names, or tweaking the grammar to better fit the description) and submit that question and move on (repeat from step 6)
8. otherwise, if the question hasn't been answered, add the question to the table and mark it as unanswered.
### collection 
9. add job title and company to a "history" table and a date of submission (prevent double-application within the same season/hiring cycle). 
10. wait for responses

## data and formats
- the data (table with questions + answers, table with submitted applications) should be easy to both read and edit manually, and should be constantly-updated (so if I paste a new answer for a question, the table that is in the script should be accepted immediately) 
- keys should be kept secret
- the model should be configurable. if there is no api key or ollama endpoint detected in .env.local, a medium size model should be pulled from huggingface (assumes a local model should be pulled. the model should be aimed for running on a colab notebook).
- for true/false questions (such as veteran status), it should be treated as another free-response question, but the answers should be true|false
