# perfectArchive

Django code base for https://theperfectline.info/

This site maintains the archive of game play for the CBS/Game Show Network television show The Perfect Line

Site is a passion project to track statistics based on podium position and player performance

This project was a learning experience for the developer as Google Gemini (2.5 Pro) was used to develop, modify and
maintain the site. Not a single line of code has been handwritten. The entire project from start to finish is being
performed through a series of prompts, tested locally then deployed.

Everything from GitHub, AWS and devOps work to 'conversations' about methodology, models and functions were discussed
and paths chosen rather than merely dictated.

# Features
## Site Template
* Site menu, different layout for desktop vs mobile
* Obfuscated login for administrators
* Footer contact info and Instagram link
* MailChimp powered newsletter sign-up

## Home Page
* Brief intro of site and game
* Last game display
* Top 3 Champion display

## Recent Games
* Paginated list of recent games, most recent to oldest
* Displays Episode title, original air date and the episode number
* Each player is shown with circles denoting correct/incorrect answers as well as preliminary rond final score
* Two players who advance to Fast Line show the number of correct/incorrect answers they made along with their final game score
* Game winner shows the number (out of 5) of items correctly placed on the Final Line along with their winnings

## Statistics
* Broken into the 3 sections of the game 

### Preliminary Rounds
* Question answer success rate is shown for each podium position for each round
* The average questions correct by all players per round are also shown 
* Placement success rate is shown by performance order (**Important Stat**)
* Correct Answer Distribution shows how many items are placed by the players collectively
* Prelim Performance by Player shows how many questions a single player gets right during their Preliminary Rounds
* How often players advance based on how many questions they got right
* Four tables with the top preliminary round scores by podium position
* A table with the average winnings by podium position, the percentage of times that player advances to the Fast Line and percentage that podium wins the game

### Fast Line
* Chart displaying the histogram of correct/incorrect scores in the Fast Line
* Average score in the Fast Line
* Top 5 performers in the Fast Line
* Come from behind statistics: The number of times the fast line winner was behind after the preliminary round, the average score overcome, the greatest score overcome and the top 5 comeback players
 
### Final Line
* Table displaying how often players get 0-5 items on the line correct with percentage and absolute number
* A leaderboard of the Top 10 players after the Fast Line as well as Winning scores

### General Stats Notes
* Most leaderboards have a "more" link which expands to twice the original list size
* All leaderboards denote the Episode number and date - those are clickable and bring users to the Game log with the specific game scrolled into position

## Analysis
* Currently, shows a human-observed analysis through GAme 20
* Future: Next analysis at Game 50, old analysis will be linked for reference

## Show Info
* Explainer on game rules and procedures for those unfamiliar with the game
* Embedded YouTube video snipet of gameplay
* National TV broadcast information
* Syndicated TV broadcast information with state-selectable drop-down
* Links to Game Show Network, Perfect Line Official and Deborah Norville social media and websites

## New stuff
* Permalinks added for each episode for easier sharing on social media

## Game Play
* Admin to enter perfect lines
* Ability to play a perfect line game
* Leaderboard to track daily, weekly, monthly leaders
* 

# ToDo

## Play Game

### Admin
* enter fast line
* enter final line

### Game Play
* Play single player fast line
* Play final line

* Play 2-player perfect line
* Play 2-player fast line

* Play 4-player perfect line
* Play against computer perfect line

* Play full game, start to finish
* Full game vs AI
* Full game vs opponent

* Mobile drag logic. Tried, failed, give another stab in future

## General
* Bug on save for tie after fast line
* Tied games stats (# ties in after 4, # ties for victory)
