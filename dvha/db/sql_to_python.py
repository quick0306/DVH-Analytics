#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from db.sql_connector import DVH_SQL


class QuerySQL:
    def __init__(self, table_name, condition_str, unique=False):
        """
        Object to generically query a specified table
        Each column is stored as a property of the object
        :param table_name: 'Beams', 'DVHs', 'Plans', or 'Rxs'
        :type table_name: str
        :param condition_str: condition in SQL syntax
        :type condition_str: str
        :param unique: If set to True, only unique values stored
        :type unique: bool

        For example, if you query 'dvhs' with condition string of "mrn = 'some_mrn'"
        you can access any column name 'some_column' with QuerySQL.some_column which will return a list of values
        for 'some_column'.  All properties contain lists with their values ordered synced, unless unique=True
        """

        table_name = table_name.lower()

        if table_name in {'beams', 'dvhs', 'plans', 'rxs'}:
            self.table_name = table_name
            self.condition_str = condition_str
            with DVH_SQL() as cnx:

                for column in cnx.get_column_names(table_name):
                    if column not in {'roi_coord_string', 'distances_to_ptv'}:  # ignored for memory since not used here
                        self.cursor = cnx.query(self.table_name,
                                                column,
                                                self.condition_str)
                        rtn_list = self.cursor_to_list()
                        if unique:
                            rtn_list = get_unique_list(rtn_list)
                        setattr(self, column, rtn_list)  # create property of QuerySQL based on SQL column name
        else:
            print('Table name in valid. Please select from Beams, DVHs, Plans, or Rxs.')

    def cursor_to_list(self):
        """
        Convert a cursor return into a list of values
        :return: queried data
        :rtype: list
        """
        rtn_list = []
        for row in self.cursor:
            if isinstance(row[0], (int, float)):
                rtn_list.append(row[0])
            else:
                rtn_list.append(str(row[0]))
        return rtn_list


def get_unique_list(input_list):
    """
    Remove duplicates in list and retain order
    :param input_list: any list of objects
    :return: input_list without duplicates
    :rtype: list
    """
    rtn_list_unique = []
    for value in input_list:
        if value not in rtn_list_unique:
            rtn_list_unique.append(value)

    return rtn_list_unique


def get_database_tree():
    """
    Query SQL to get all columns of each table
    :return: column data sorted by table
    :rtype: dict
    """
    with DVH_SQL() as cnx:
        tree = {table: cnx.get_column_names(table) for table in cnx.tables}
    return tree

