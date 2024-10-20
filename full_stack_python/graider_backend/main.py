import os
import sys

current_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_directory)

from aiTools import aiTools


def main():

    question = "Question 2 (15 marks total)\
We will be using a modified version of the data set in Q1 for this question. Round all answers to 3\
decimal places. Use the data set toyota_modified_forQ2.txt posted on Canvas.\
a) (6 marks) Which two numeric variables have the strongest association with the selling price\
of the vehicles (treat year as numeric)? For each of the two variables, draw a scatterplot and\
report the correlation coefficient. Interpret the correlation coefficients obtained in the context\
of the question. Also describe the shape of the trend observed in the scatterplots.\
b) (1 mark) To investigate the relationship between price and mileage of the used cars, fit a\
least squares regression line that predicts price from mileage, and report the equation that\
represents this line.\
c) (1 mark) Plot the regression line from part (b) on the scatterplot. Make sure to include the\
plot in your solution.\
d) (2 marks) Based on the regression line obtained in part (b), what is the predicted price of a\
car with 150k mileage? Explain whether this prediction is legitimate.\
e) (2 marks) Draw an appropriate plot to assess the linear fit. Do you notice any issues?\
f ) (3 marks) Notice that there are two car models in the dataset: ”Yaris” and ”C-HR”. Fit a\
regression line to each of the two models (predicting price from mileage), and plot these two\
lines on the scatterplot (the same scatterplot as in part (c)). Report the equations of these\
two regression lines, and include the scatterplot in your solution. Which method (fitting one\
overall regression line in (b) versus fitting two separate regression lines in this part) do you\
think works better for our dataset? Briefly justify your choice."
    listOfQuestionParts = aiTools.segregateQuestion(question)

    print(1)

    for qp in listOfQuestionParts:
        print(qp.id, "\t", qp.text, "\t", qp.marks, "\n")

if __name__ == "__main__":
    main()