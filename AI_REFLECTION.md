# Section 4: AI Reflection

### 1. What did you use AI for across the four sections?

- **Section 1 – System Design:** I used AI to help break down the requirements, plan the system architecture, identify the core models, and outline the API endpoints.
- **Section 2 – API Implementation:** I used AI to speed up the initial Django REST Framework setup, generate a working prototype, structure the modules, assist with debugging, and write automated tests for the booking logic.
- **Section 3 – Deployment and CI/CD:** I used AI to help plan the configuration and deployment process and to document the steps required to run the application.
- **Section 4 – Documentation and Reflection:** I used AI to help draft the README, articulate the design decisions, and organize the project documentation.

Overall, AI reduced the time I spent on repetitive setup and documentation, which allowed me to focus on implementation, testing, and verifying that the application behaved correctly.

### 2. Give one example where an AI suggestion improved your work. What did you prompt it with?

AI helped me scaffold the project modules and produce a working prototype quickly. This gave me a functional starting point rather than building every component from scratch.

My prompt asked it to set up a Django REST Framework project for a clinic appointment booking system, organize the project into modules, implement the required endpoints, and prepare an initial set of tests.

This improved my productivity by reducing time spent on boilerplate code, so I could concentrate on the booking requirements and validation logic.

### 3. Give one example where AI output was wrong or incomplete, and how you caught it.

The AI-generated code did not fully match the project requirements. The validation logic was inconsistent with the booking rules, and the model definitions were not correct. As a result, the AI also generated endpoints that were not required for the system.

I caught these issues while reviewing the generated code against the requirements and testing the booking workflow. I corrected the validation logic, fixed the models so they reflected the intended design, and removed the unnecessary endpoints. I then retested the application to confirm that the API exposed only the required functionality and enforced the booking rules correctly.

This reinforced the importance of reviewing AI-generated code against the actual requirements rather than assuming it is complete or correct.

### 4. Name two decisions you made without AI. Why did you trust your own judgment there?

**Decision 1: Separating the date-picker output into distinct date and time values.**

I split the date-picker output into separate date and time fields to make the inputs easier to work with and to speed up manual testing. This also made it easier to test different appointment dates and time slots independently.

I trusted my judgment because I was testing the booking workflow directly and could see first-hand how this approach improved the process.

**Decision 2: Manually correcting the Swagger documentation configuration.**

When the AI-generated implementation did not work as expected, I chose to investigate and fix the Swagger URL configuration myself.

I trusted my judgment because I could reproduce the issue, inspect the Django URL configuration, and verify the fix by accessing the documentation endpoint. I did not consider the task complete until I had tested the result.