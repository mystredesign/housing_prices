import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns
from sklearn import preprocessing
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import(
    LabelEncoder, LabelBinarizer, MinMaxScaler, StandardScaler, LabelEncoder, Imputer, OneHotEncoder
)
# CategoricalEncoder
from sklearn_pandas import DataFrameMapper
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
#from sklearn.ensemble import LGBMRegressor

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import seaborn as sns
from sklearn import metrics
from sklearn.feature_extraction.text import CountVectorizer

from sklearn.base import BaseEstimator, TransformerMixin


def train_validate_test_split(df, train_percent=.8, validate_percent=.05, seed=None):
    np.random.seed(seed)
    perm = np.random.permutation(len(df))
    m = len(df.index)
    train_end = int(train_percent * m)
    validate_end = int(validate_percent * m) + train_end
    df_train = df.iloc[perm[:train_end]]
    df_validate = df.iloc[perm[train_end:validate_end]]
    df_test = df.iloc[perm[validate_end:]]
    return df_train, df_validate, df_test


class RemoveNotUsefulFields(BaseEstimator, TransformerMixin):
    def __init__(self, not_useful_fields):
        self.not_useful_fields = not_useful_fields

    def fit(self, df, y):
        return self

    def transform(self, df):
        return remove_not_useful_fields(df, self.not_useful_fields)


class ConvertDates(BaseEstimator, TransformerMixin):
    #: TODO: Generalize this to allow for different date-type outputs to become features
    def __init__(self, date_fields):
        self.date_fields = date_fields
        self.new_date_fields = []

    def fit(self, df, y):
        return self

    def transform(self, df):
        df, new_date_fields = convert_dates_helper(df, self.date_fields)
        self.new_date_fields = new_date_fields
        return df


class ZeroToNanFields(BaseEstimator, TransformerMixin):
    def __init__(self, zero_to_nan_fields):
        self.zero_to_nan_fields = zero_to_nan_fields

    def fit(self, df, y):
        return self

    def transform(self, df):
        # Replace zeros with nan for imputation down the way
        if self.zero_to_nan_fields is not None:
            for field in self.zero_to_nan_fields:
                if field in df.keys():
                    df[df[field] == 0, field] = np.nan
        return df


class NanToZeroFields(BaseEstimator, TransformerMixin):
    def __init__(self, nan_to_zero_fields):
        self.nan_to_zero_fields = nan_to_zero_fields

    def fit(self, df, y):
        return self

    def transform(self, df):
        # Replace zeros with nan for imputation down the way
        if self.nan_to_zero_fields is not None:
            for field in self.nan_to_zero_fields:
                if field in df.keys():
                    df.loc[pd.isnull(df[field]), field] = 0
        return df


class KeepRequiredFields(BaseEstimator, TransformerMixin):
    def __init__(self, required_fields):
        self.required_fields = required_fields

    def fit(self, df, y):
        return self

    def transform(self, df):
        for key in iter(df.keys()):
            if key not in self.required_fields:
                df.drop(labels=key, axis=1, inplace=True)
        return df


class PrepareData(BaseEstimator, TransformerMixin):
    def __init__(self, required_fields,
                 date_fields=None,
                 zero_to_nan_fields=None,
                 nan_to_zero_fields=None):
        self.keep_required_fields = KeepRequiredFields(required_fields)
        self.nan_to_zero = NanToZeroFields(
            nan_to_zero_fields=nan_to_zero_fields)
        self.zero_to_nan = ZeroToNanFields(
            zero_to_nan_fields=zero_to_nan_fields)
        # TODO: use the ConvertDates.new_date_fields and then plug in with featurize
        self.convert_dates = ConvertDates(date_fields)
        self.impute_zip_codes = ImputeZipCodes()
    def fit(self, df, y):
        self.zero_to_nan.fit(df, y)
        self.nan_to_zero.fit(df, y)
        self.convert_dates.fit(df, y)
        self.impute_zip_codes.fit(df, y)
        return self

    def transform(self, df):
        df = self.keep_required_fields.transform(df)
        df = self.zero_to_nan.transform(df)
        df = self.nan_to_zero.transform(df)
        df = self.convert_dates.transform(df)
        df = self.impute_zip_codes.transform(df)
        return df


class ImputeZipCodes(BaseEstimator, TransformerMixin):
    # This class will make zipcodes become
    # for data not containing the zipcode, it will find the
    # center of zipcode lat-long data and estimate a zipcode

    # A better way would be to use a web API to search the address and extract the zipcode
    # I'm going to do this first.

    # For the future: make this a general imputer that provides classification for training data
    # using clustering methods.

    def __init__(self):
        self.zip_code_lat_long_df = pd.DataFrame()

    def fit(self, X, y):
        self.zip_code_lat_long_df = \
            pd.groupby(X, 'zipcode')['latitude',
                                     'longitude'].mean().add_suffix('_mean')
        return self

    def transform(self, X):
        bad_index = ~X['zipcode'].isin(self.zip_code_lat_long_df.index)
        dd = X[bad_index][['latitude', 'longitude']]

        if len(dd) == 0:
            # No unseen zipcodes were found
            return X

        ndx = (dd[['latitude', 'longitude']]).reset_index().apply(
            lambda x: smallest_gcd_distance_ndx(
                self.zip_code_lat_long_df.latitude_mean.values,
                self.zip_code_lat_long_df.longitude_mean.values,
                x[0], x[1]),
            axis=1)
        X.loc[bad_index, 'zipcode'] = \
            self.zip_code_lat_long_df.iloc[ndx].index
        return X


def smallest_gcd_distance_ndx(lat1, lng1, lat2, lng2):
    '''
    find the array index of the smallest great-circal distance
    '''
    return np.argmin(gcd_vec(lat1, lng1, lat2, lng2))


def gcd_vec(lat1, lng1, lat2, lng2):
    '''
    Calculate great circle distance.
    http://www.johndcook.com/blog/python_longitude_latitude/

    Parameters
    ----------
    lat1, lng1, lat2, lng2: float or array of float

    Returns
    -------
    distance:
      distance from ``(lat1, lng1)`` to ``(lat2, lng2)`` in kilometers.
    '''
    # python2 users will have to use ascii identifiers
    f1 = np.deg2rad(90 - lat1)
    f2 = np.deg2rad(90 - lat2)

    t1 = np.deg2rad(lng1)
    t2 = np.deg2rad(lng2)

    cos = (np.sin(f1) * np.sin(f2) * np.cos(t1 - t2) +
           np.cos(f1) * np.cos(f2))
    arc = np.arccos(cos)
    return arc * 6373


def remove_not_useful_fields(df, not_useful_fields=None):
    # This function will remove entire columns of a dataframe that are
    # not needed for the analysis (meta or highly duplicated info)
    if not_useful_fields is None:
        return df

    try:  # Handle different versions of pandas
        df.drop(columns=not_useful_fields, inplace=True)
    except TypeError:
        df.drop(not_useful_fields, axis=1, inplace=True)

    return df


def convert_dates_helper(df, date_fields):
    # This function will convert date strings into numerical
    # forms that are more amenable for use by ML models
    if date_fields is None:
        return df

    new_fields = []
    for field in date_fields:
        if field not in df.keys():
            print("Warning, field {} not in dataframe".format(field))
            continue
        d = pd.Series(pd.to_datetime(df[field], format='%Y-%m-%d'))

        df[field + 'DayOfWeek'] = d.dt.dayofweek
        df[field + 'WeekOfYear'] = d.dt.weekofyear
        df[field + 'Month'] = d.dt.month
        df[field + 'Year'] = d.dt.year
        new_fields.append(field + 'DayOfWeek')
        new_fields.append(field + 'WeekOfYear')
        new_fields.append(field + 'Month')
        new_fields.append(field + 'Year')
        #df.drop(labels=field, axis=1, inplace=True)

    return df, new_fields

class Identity(BaseEstimator, TransformerMixin):
    def __init__(self):
        None
    def fit(self, X, y):
        return self
    def transform(self, X):
        return X


def imputerize_df(features, df_out):
    # TODO: This needs to be interal to prepare_data so that we can keep fields consistent
    # namely, this is not general enough
    print('Imputerize')
    transformations = [
        ('hasPriorSale', Imputer(missing_values=np.nan, strategy="median", axis=0)),
        ('latitude', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('longitude', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('bedrooms', Imputer(missing_values=np.nan, strategy="median", axis=0)),
        ('bathrooms', Imputer(missing_values=np.nan, strategy="median", axis=0)),
        ('rooms', Imputer(missing_values=np.nan, strategy="median", axis=0)),
        ('squareFootage', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('lotSize', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('yearBuilt', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('squareFootageOverLotSize', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('bathroomsPerRooms', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('roomsPerSquareFootage', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('lastSaleAmount', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('lastSaleDateDayOfWeek', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('lastSaleDateWeekOfYear', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('lastSaleDateMonth', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('lastSaleDateYear', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('priorSaleAmount', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('priorSaleDateDayOfWeek', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('priorSaleDateWeekOfYear', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('priorSaleDateMonth', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('priorSaleDateYear', Imputer(missing_values=np.nan, strategy="mean", axis=0)),
        ('zipcode', Identity()),
    ]
    for feature in features:
        transform_fields = [transform[0] for transform in transformations] 
        #transform_fields = [item for sublist in transform_fields for item in sublist if len(item)>1]
        if feature not in transform_fields:
            print("Warning, feature {} not in the list {}".format(feature, transform_fields))
    return DataFrameMapper(filter(lambda x: x[0] in features, transformations), df_out=df_out)


def featurize_df(features, df_out):
    print('Featurize')
    # TODO: This needs to be interal to prepare_data so that we can keep fields consistent
    # namely, this is not general enough
    day_range = [0, 6]
    week_range = [0, 52]
    month_range = [0, 11]
    year_range = [1900, 2020]
    transformations = [
        ('zipcode', LabelEncoder()),
        ('hasPriorSale', LabelEncoder()),
        ('latitude', StandardScaler()),
        ('longitude', StandardScaler()),
        ('bedrooms', StandardScaler()),
        ('bathrooms', StandardScaler()),
        ('rooms', StandardScaler()),
        ('squareFootage', StandardScaler()),
        ('lotSize', StandardScaler()),
        ('yearBuilt', MinMaxScaler()),
        ('squareFootageOverLotSize', StandardScaler()),
        ('bathroomsPerRooms', StandardScaler()),
        ('roomsPerSquareFootage', StandardScaler()),
        ('lastSaleAmount', StandardScaler()),
        ('lastSaleDateDayOfWeek', MinMaxScaler()),
        ('lastSaleDateWeekOfYear', MinMaxScaler()),
        ('lastSaleDateMonth', MinMaxScaler()),
        ('lastSaleDateYear', MinMaxScaler()),
        ('priorSaleAmountx', StandardScaler()),
        ('priorSaleDateDayOfWeek', MinMaxScaler()),
        ('priorSaleDateWeekOfYear', MinMaxScaler()),
        ('priorSaleDateMonth', MinMaxScaler()),
        ('priorSaleDateYear', MinMaxScaler()),
    ]
    for feature in features:
        transform_fields = np.array(transformations)[:, 0].tolist()
        #transform_fields = [item for sublist in transform_fields for item in sublist if len(item)>1]
        if feature not in transform_fields:
            print("Warning, feature {} not in the list {}".format(feature, transform_fields))
    return DataFrameMapper(filter(lambda x: x[0] in features, transformations), df_out=df_out)


class StreetVectorizer(BaseEstimator, TransformerMixin):
    def __init__(self):
        self.cv = CountVectorizer(
            analyzer='word', token_pattern='[A-Za-z]{3,}')

    def fit(self, df, y):
        self.cv.fit(df['address'])
        return self

    def transform(self, df):
        return self.cv.transform(df['address'])


def print_metrics(y, y_pred):
    print("Sqrt mse: {}".format(np.sqrt(metrics.mean_squared_error(y, y_pred))))
    print("Mean absolute error: {}".format(
        metrics.mean_absolute_error(y, y_pred)))
    print("R2 score: {}".format(metrics.r2_score(y, y_pred)))
    print("Absolute mean relative error: {}".format(
        abs_mean_relative_error(y, y_pred)))


def abs_mean_relative_error(y, y_pred):
    return np.mean(np.abs(y - y_pred) / (y))

# TODO: Evaluate different feature sets.
# TODO: error handling of input data types
# TODO: Ensure more broad testing of input data types (Nan/Zero handling)
# TODO: Improve plotting/metric evaluation
# TODO: Github repository
# TODO: Robust deployment on different machine
