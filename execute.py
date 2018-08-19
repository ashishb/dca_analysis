# Python 2 and 3, print compatibility
from __future__ import print_function
from datetime import datetime
from dateutil import relativedelta

import docopt
import json
import os
import sys

_verbose = False

_DCA_DAILY = 1
_DCA_WEEKLY = 2
_DCA_MONTHLY = 3
_DCA_YEARLY = 4

USAGE_STRING = """

Usage:
    execute.py [options] <security_name>

Options:
    -s, --start_date=<start_date>            Start date of the investing (YYYY-mm-dd format)
    -e, --end_date=<end_date>                End date of the investing (YYYY-mm-dd format)
    -v, --verbose                 Verbose mode
"""


class AlphaVantage:
    @staticmethod
    def get_time_series_data(security_name):
        file_name = "%s_data_full.json" % security_name
        file_name = file_name.lower()
        if not os.path.isfile(file_name):
            cmd = "curl 'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&outputsize=compact&symbol=%s&apikey=<api_key>' > %s" % (
                security_name, file_name)
            raise AssertionError(
                'File \"%s\" does not exist, first get the Alpha Vantage key at '
                'https://www.alphavantage.co/support/#api-keyand then generate the file '
                'with command\n \"%s\"' % (file_name, cmd))
        json_data = json.load(open(file_name, 'r'))
        return json_data.get("Time Series (Daily)")

    @staticmethod
    def get_closing_price(time_series_data, date):
        date_string = date.strftime("%Y-%m-%d")
        data = time_series_data.get(date_string)
        if data is None:
            if _verbose:
                print("No data found for date %s" % date_string)
            return None
        return float(data.get("4. close"))


def get_new_date(current_date, strategy):
    if strategy == _DCA_DAILY:
        new_date = current_date + relativedelta.relativedelta(days=+1)
    elif strategy == _DCA_WEEKLY:
        new_date = current_date + relativedelta.relativedelta(weeks=+1)
    elif strategy == _DCA_MONTHLY:
        new_date = current_date + relativedelta.relativedelta(months=+1)
    elif strategy == _DCA_YEARLY:
        new_date = current_date + relativedelta.relativedelta(years=+1)
    else:
        raise AssertionError("Unexpected strategy %d" % strategy)

    new_date = adjust_to_next_weekday(new_date)
    return new_date


# Skip over the Saturday and Sunday.
def adjust_to_next_weekday(new_date):
    # Monday = 1 in ISO weekday
    if new_date.isoweekday() == 6:
        new_date = new_date + relativedelta.relativedelta(days=+2)
    if new_date.isoweekday() == 7:
        new_date = new_date + relativedelta.relativedelta(days=+1)
    return new_date


# If no closing price is found then use the closing price of the next day.
# Since we are skipping over the weekends, this is only going to impact a few holidays (~10) days and hence,
# hopefully, does not distort daily DCA data (for which we will do multiple purchases).
def get_closing_price(time_series_data, current_date):
    price = AlphaVantage.get_closing_price(time_series_data, current_date)

    adjusted_date = current_date
    while price is None:
        adjusted_date = get_new_date(adjusted_date, _DCA_DAILY)
        price = AlphaVantage.get_closing_price(time_series_data, adjusted_date)

    return price


# Returns fraction and not the %age gains
def generate_annual_gains(invested_amount, final_amount, duration):
    num_years = duration.days / 365.0
    # simple_gains = ((final_amount - invested_amount) / invested_amount) / num_years
    cagr = (final_amount / invested_amount) ** (1 / num_years) - 1.0
    return cagr


def get_result(security_name, strategy, start_date, end_date):
    time_series_data = AlphaVantage.get_time_series_data(security_name)

    # Any amount is fine here, it won't matter in the gains calculation.
    amount_invested_per_purchase = 100.0
    invested_amount = 0.0
    num_purchased_shares = 0
    current_date = adjust_to_next_weekday(start_date)
    while current_date <= end_date:
        invested_amount += amount_invested_per_purchase
        purchase_price = get_closing_price(time_series_data, current_date)
        num_purchased_shares += amount_invested_per_purchase / purchase_price
        if _verbose:
            print("Made a purchase of %.2f shares at %.2f price (amount = %d) on %s" %
                  (num_purchased_shares, purchase_price, num_purchased_shares * purchase_price,
                   current_date.strftime("%Y-%m-%d")))
        current_date = get_new_date(current_date, strategy)

    final_share_price = get_closing_price(time_series_data, end_date)
    final_amount = num_purchased_shares * final_share_price
    # Gains (or losses, if negative)
    gains = final_amount - invested_amount

    if _verbose:
        print("Total invested amount = %.2f, final amount = %.2f (final share price = %.2f), gains = %.2f over %s duration" %
              (invested_amount, final_amount, final_share_price, gains, end_date - start_date))

    return generate_annual_gains(invested_amount, final_amount, end_date - start_date)


def get_string(strategy):
    if strategy == _DCA_DAILY:
        return "DCA daily"
    elif strategy == _DCA_WEEKLY:
        return "DCA weekly"
    elif strategy == _DCA_MONTHLY:
        return "DCA monthly"
    elif strategy == _DCA_YEARLY:
        return "DCA yearly"
    else:
        raise AssertionError("Unexpected strategy %d" % strategy)


def main():
    global _verbose
    args = docopt.docopt(USAGE_STRING, version='1.0.0')
    security_name = args['<security_name>']

    _verbose = True if args['--verbose'] else False

    if not args['--start_date']:
        raise AssertionError("start_date (YYYY-mm-dd) should be provided")

    if not args['--end_date']:
        raise AssertionError("end_date (YYYY-mm-dd) should be provided")

    start_date = datetime.strptime(args['--start_date'], '%Y-%m-%d')
    end_date = datetime.strptime(args['--end_date'], '%Y-%m-%d')

    if start_date > datetime.now():
        print("Start  date cannot be more than current date")
        sys.exit(1)

    if end_date > datetime.now():
        print("End date cannot be more than current date")
        sys.exit(1)

    if start_date > end_date:
        print("Start date cannot be more than end date")
        sys.exit(1)

    for strategy in [_DCA_DAILY, _DCA_WEEKLY, _DCA_MONTHLY, _DCA_YEARLY]:
        if _verbose:
            print("Analyzing \"%s\" security for \"%s\" investment strategy from %s to %s" %
                  (security_name, strategy, start_date, end_date))

        print("Result of \"%s\" security with \"%s\" investment strategy is %.2f%%" %
              (security_name, get_string(strategy), 100 * get_result(security_name, strategy, start_date, end_date)))


if __name__ == "__main__":
    main()
