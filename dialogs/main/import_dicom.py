import wx
import wx.adv
from db.dicom_importer import DICOM_Importer
from db.dicom_parser import DICOM_Parser
from os.path import isdir
from options import get_settings, parse_settings_file
from wx.lib.agw.customtreectrl import CustomTreeCtrl
from wx.lib.agw.customtreectrl import TR_AUTO_CHECK_CHILD, TR_AUTO_CHECK_PARENT, TR_DEFAULT_STYLE
from tools.utilities import datetime_to_date_string
from db.sql_connector import DVH_SQL
from tools.roi_name_manager import DatabaseROIs
from dateutil.parser import parse as parse_date
from datetime import date as datetime_obj


class ImportDICOM_Dialog(wx.Dialog):
    def __init__(self, *args, **kwds):
        wx.Dialog.__init__(self, None, title='Import DICOM')

        self.SetSize((1350, 800))

        self.parsed_dicom_data = {}
        self.selected_uid = None

        self.roi_map = DatabaseROIs()
        self.selected_roi = None

        abs_file_path = get_settings('import')
        self.start_path = parse_settings_file(abs_file_path)['inbox']

        self.checkbox = {}
        keys = ['birth_date', 'sim_study_date', 'physician', 'tx_site', 'rx_dose']
        for key in keys:
            self.checkbox['%s_1' % key] = wx.CheckBox(self, wx.ID_ANY, "Apply to all studies")
            self.checkbox['%s_2' % key] = wx.CheckBox(self, wx.ID_ANY, "Only if missing")
        self.global_plan_over_rides = {key: {'value': None, 'only_if_missing': False} for key in keys}

        self.text_ctrl_directory = wx.TextCtrl(self, wx.ID_ANY, '', style=wx.TE_READONLY)

        cnx = DVH_SQL()
        self.input = {'mrn': wx.TextCtrl(self, wx.ID_ANY, ""),
                      'study_instance_uid': wx.TextCtrl(self, wx.ID_ANY, ""),
                      'birth_date': wx.TextCtrl(self, wx.ID_ANY, ""),
                      'sim_study_date': wx.TextCtrl(self, wx.ID_ANY, ""),
                      'physician': wx.ComboBox(self, wx.ID_ANY, choices=cnx.get_unique_values('Plans', 'physician'),
                                               style=wx.CB_DROPDOWN),
                      'tx_site': wx.ComboBox(self, wx.ID_ANY, choices=cnx.get_unique_values('Plans', 'tx_site'),
                                             style=wx.CB_DROPDOWN),
                      'rx_dose': wx.TextCtrl(self, wx.ID_ANY, "")}
        self.input['physician'].SetValue('')
        self.input['tx_site'].SetValue('')
        self.button_apply_plan_data = wx.Button(self, wx.ID_ANY, "Apply")
        self.disable_inputs()

        self.button_browse = wx.Button(self, wx.ID_ANY, u"Browse…")
        self.checkbox_subfolders = wx.CheckBox(self, wx.ID_ANY, "Search within subfolders")
        self.panel_study_tree = wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.gauge = wx.Gauge(self, -1, 100)
        self.button_import = wx.Button(self, wx.ID_ANY, "Import")
        self.button_cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")

        self.panel_roi_tree = wx.Panel(self, wx.ID_ANY, style=wx.BORDER_SUNKEN)
        self.input_roi = {'physician': wx.ComboBox(self, wx.ID_ANY, choices=[], style=wx.CB_DROPDOWN),
                          'type': wx.ComboBox(self, wx.ID_ANY, choices=cnx.get_unique_values('DVHs', 'roi_type'), style=wx.CB_DROPDOWN)}
        self.input_roi['type'].SetValue('')
        self.button_apply_roi = wx.Button(self, wx.ID_ANY, "Apply")
        self.disable_roi_inputs()

        cnx.close()

        styles = TR_AUTO_CHECK_CHILD | TR_AUTO_CHECK_PARENT | TR_DEFAULT_STYLE
        self.tree_ctrl_import = CustomTreeCtrl(self.panel_study_tree, wx.ID_ANY, agwStyle=styles)
        self.tree_ctrl_import.SetBackgroundColour(wx.WHITE)

        self.tree_ctrl_roi = CustomTreeCtrl(self.panel_roi_tree, wx.ID_ANY, agwStyle=styles)
        self.tree_ctrl_roi.SetBackgroundColour(wx.WHITE)
        self.tree_ctrl_roi_root = self.tree_ctrl_roi.AddRoot('RT Structures', ct_type=1)

        self.checkbox_include_uncategorized = wx.CheckBox(self, wx.ID_ANY, "Import uncategorized ROIs")

        self.__do_bind()
        self.__set_properties()
        self.__do_layout()

        self.dicom_dir = DICOM_Importer('', self.tree_ctrl_import, self.tree_ctrl_roi, self.tree_ctrl_roi_root)
        self.parse_directory()

    def __do_bind(self):
        self.Bind(wx.EVT_BUTTON, self.on_browse, id=self.button_browse.GetId())

        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_file_tree_select, id=self.tree_ctrl_import.GetId())
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_roi_tree_select, id=self.tree_ctrl_roi.GetId())

        self.Bind(wx.EVT_TEXT, self.on_mrn_change, id=self.input['mrn'].GetId())
        self.Bind(wx.EVT_TEXT, self.on_uid_change, id=self.input['study_instance_uid'].GetId())
        self.Bind(wx.EVT_TEXT, self.on_birth_date_change, id=self.input['birth_date'].GetId())
        self.Bind(wx.EVT_TEXT, self.on_sim_study_date_change, id=self.input['sim_study_date'].GetId())
        self.Bind(wx.EVT_TEXT, self.on_physician_change, id=self.input['physician'].GetId())
        self.Bind(wx.EVT_TEXT, self.on_tx_site_change, id=self.input['tx_site'].GetId())
        self.Bind(wx.EVT_TEXT, self.on_rx_change, id=self.input['rx_dose'].GetId())

        self.Bind(wx.EVT_COMBOBOX, self.on_physician_change, id=self.input['physician'].GetId())
        self.Bind(wx.EVT_COMBOBOX, self.on_tx_site_change, id=self.input['tx_site'].GetId())

        self.Bind(wx.EVT_BUTTON, self.on_apply_plan, id=self.button_apply_plan_data.GetId())
        self.Bind(wx.EVT_BUTTON, self.on_apply_roi, id=self.button_apply_roi.GetId())

        for key in ['birth_date', 'sim_study_date', 'physician', 'tx_site', 'rx_dose']:
            self.Bind(wx.EVT_CHECKBOX, self.on_check_apply_all, id=self.checkbox['%s_1' % key].GetId())
            self.Bind(wx.EVT_CHECKBOX, self.on_check_apply_all, id=self.checkbox['%s_2' % key].GetId())

    def __set_properties(self):
        self.checkbox_subfolders.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT,
                                                 wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, 0, ""))
        self.checkbox_subfolders.SetValue(1)
        self.checkbox_include_uncategorized.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT,
                                                 wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, 0, ""))
        self.checkbox_include_uncategorized.SetValue(1)

        for checkbox in self.checkbox.values():
            checkbox.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, 0, ""))

    def __do_layout(self):
        self.label = {}
        sizer_wrapper = wx.BoxSizer(wx.VERTICAL)
        sizer_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sizer_main = wx.BoxSizer(wx.HORIZONTAL)
        sizer_roi_map_wrapper = wx.BoxSizer(wx.HORIZONTAL)
        sizer_roi_map = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "ROI Mapping for Selected Study"), wx.VERTICAL)
        sizer_selected_roi = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "Map for Selected ROI"), wx.VERTICAL)
        sizer_roi_type = wx.BoxSizer(wx.VERTICAL)
        sizer_physician_roi = wx.BoxSizer(wx.VERTICAL)
        sizer_roi_tree = wx.BoxSizer(wx.HORIZONTAL)
        sizer_plan_data_wrapper = wx.BoxSizer(wx.HORIZONTAL)
        sizer_plan_data = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "Plan Data for Selected Study"), wx.VERTICAL)
        sizer_rx = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.VERTICAL)
        sizer_checkbox_rx = wx.BoxSizer(wx.HORIZONTAL)
        sizer_tx_site = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.VERTICAL)
        sizer_tx_site_checkbox = wx.BoxSizer(wx.HORIZONTAL)
        sizer_physician = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.VERTICAL)
        sizer_physician_checkbox = wx.BoxSizer(wx.HORIZONTAL)
        sizer_sim_study_date = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.VERTICAL)
        sizer_sim_study_date_checkbox = wx.BoxSizer(wx.HORIZONTAL)
        sizer_birth_date = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.VERTICAL)
        sizer_birth_date_checkbox = wx.BoxSizer(wx.HORIZONTAL)
        sizer_uid = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.VERTICAL)
        sizer_mrn = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, ""), wx.VERTICAL)
        sizer_browse_and_tree = wx.BoxSizer(wx.VERTICAL)
        sizer_studies = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "Studies"), wx.VERTICAL)
        sizer_progress = wx.BoxSizer(wx.HORIZONTAL)
        sizer_tree = wx.BoxSizer(wx.HORIZONTAL)
        sizer_dicom_import_directory = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, "DICOM Import Directory"),
                                                         wx.VERTICAL)
        sizer_directory = wx.BoxSizer(wx.VERTICAL)
        sizer_browse = wx.BoxSizer(wx.HORIZONTAL)
        sizer_browse.Add(self.text_ctrl_directory, 1, wx.ALL | wx.EXPAND, 5)
        sizer_browse.Add(self.button_browse, 0, wx.ALL, 5)
        sizer_directory.Add(sizer_browse, 1, wx.EXPAND, 0)
        sizer_directory.Add(self.checkbox_subfolders, 0, wx.LEFT, 10)
        sizer_dicom_import_directory.Add(sizer_directory, 1, wx.EXPAND, 0)
        sizer_browse_and_tree.Add(sizer_dicom_import_directory, 0, wx.ALL | wx.EXPAND, 10)
        label_note = wx.StaticText(self, wx.ID_ANY,
                                   "NOTE: Only the latest files will be used for a given study instance UID, "
                                   "all others ignored.")
        label_note.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, 0, ""))
        sizer_studies.Add(label_note, 0, wx.ALL, 5)
        sizer_tree.Add(self.tree_ctrl_import, 1, wx.EXPAND, 0)
        self.panel_study_tree.SetSizer(sizer_tree)
        sizer_studies.Add(self.panel_study_tree, 1, wx.ALL | wx.EXPAND, 5)
        self.label_progress = wx.StaticText(self, wx.ID_ANY, "Progress: Status message")
        self.label_progress.SetFont(wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, 0, ""))
        sizer_progress.Add(self.label_progress, 1, 0, 0)
        sizer_progress.Add(self.gauge, 1, wx.LEFT | wx.EXPAND, 40)
        sizer_studies.Add(sizer_progress, 0, wx.EXPAND, 0)
        sizer_browse_and_tree.Add(sizer_studies, 1, wx.BOTTOM | wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        sizer_main.Add(sizer_browse_and_tree, 1, wx.EXPAND, 0)

        self.label['mrn'] = wx.StaticText(self, wx.ID_ANY, "MRN:")
        sizer_mrn.Add(self.label['mrn'], 0, 0, 0)
        sizer_mrn.Add(self.input['mrn'], 0, wx.EXPAND, 0)

        sizer_plan_data.Add(sizer_mrn, 1, wx.ALL | wx.EXPAND, 5)
        self.label['study_instance_uid'] = wx.StaticText(self, wx.ID_ANY, "Study Instance UID:")
        sizer_uid.Add(self.label['study_instance_uid'], 0, 0, 0)
        sizer_uid.Add(self.input['study_instance_uid'], 0, wx.EXPAND, 0)

        sizer_plan_data.Add(sizer_uid, 1, wx.ALL | wx.EXPAND, 5)
        self.label['birth_date'] = wx.StaticText(self, wx.ID_ANY, "Birthdate:")
        sizer_birth_date.Add(self.label['birth_date'], 0, 0, 0)
        sizer_birth_date.Add(self.input['birth_date'], 0, 0, 0)
        sizer_birth_date_checkbox.Add(self.checkbox['birth_date_1'], 0, wx.RIGHT, 20)
        sizer_birth_date_checkbox.Add(self.checkbox['birth_date_2'], 0, 0, 0)
        sizer_birth_date.Add(sizer_birth_date_checkbox, 1, wx.EXPAND, 0)
        sizer_plan_data.Add(sizer_birth_date, 1, wx.ALL | wx.EXPAND, 5)

        self.label['sim_study_date'] = wx.StaticText(self, wx.ID_ANY, "Sim Study Date:")
        sizer_sim_study_date.Add(self.label['sim_study_date'], 0, 0, 0)
        sizer_sim_study_date.Add(self.input['sim_study_date'], 0, 0, 0)
        sizer_sim_study_date_checkbox.Add(self.checkbox['sim_study_date_1'], 0, wx.RIGHT, 20)
        sizer_sim_study_date_checkbox.Add(self.checkbox['sim_study_date_2'], 0, 0, 0)
        sizer_sim_study_date.Add(sizer_sim_study_date_checkbox, 1, wx.EXPAND, 0)
        sizer_plan_data.Add(sizer_sim_study_date, 1, wx.ALL | wx.EXPAND, 5)

        self.label['physician'] = wx.StaticText(self, wx.ID_ANY, "Physician:")
        sizer_physician.Add(self.label['physician'], 0, 0, 0)
        sizer_physician.Add(self.input['physician'], 0, 0, 0)
        sizer_physician_checkbox.Add(self.checkbox['physician_1'], 0, wx.RIGHT, 20)
        sizer_physician_checkbox.Add(self.checkbox['physician_2'], 0, 0, 0)
        sizer_physician.Add(sizer_physician_checkbox, 1, wx.EXPAND, 0)
        sizer_plan_data.Add(sizer_physician, 1, wx.ALL | wx.EXPAND, 5)

        self.label['tx_site'] = wx.StaticText(self, wx.ID_ANY, "Tx Site:")
        sizer_tx_site.Add(self.label['tx_site'], 0, 0, 0)
        sizer_tx_site.Add(self.input['tx_site'], 0, wx.EXPAND, 0)
        sizer_tx_site_checkbox.Add(self.checkbox['tx_site_1'], 0, wx.RIGHT, 20)
        sizer_tx_site_checkbox.Add(self.checkbox['tx_site_2'], 0, 0, 0)
        sizer_tx_site.Add(sizer_tx_site_checkbox, 1, wx.EXPAND, 0)
        sizer_plan_data.Add(sizer_tx_site, 1, wx.ALL | wx.EXPAND, 5)

        self.label['rx_dose'] = wx.StaticText(self, wx.ID_ANY, "Rx Dose (Gy):")
        sizer_rx.Add(self.label['rx_dose'], 0, 0, 0)
        sizer_rx.Add(self.input['rx_dose'], 0, 0, 0)
        sizer_checkbox_rx.Add(self.checkbox['rx_dose_1'], 0, wx.RIGHT, 20)
        sizer_checkbox_rx.Add(self.checkbox['rx_dose_2'], 0, 0, 0)
        sizer_rx.Add(sizer_checkbox_rx, 1, wx.EXPAND, 0)
        sizer_plan_data.Add(sizer_rx, 1, wx.ALL | wx.EXPAND, 5)
        sizer_plan_data.Add(self.button_apply_plan_data, 0, wx.ALIGN_CENTER | wx.ALL | wx.EXPAND, 5)
        sizer_plan_data_wrapper.Add(sizer_plan_data, 1, wx.ALL | wx.EXPAND, 10)
        sizer_main.Add(sizer_plan_data_wrapper, 1, wx.EXPAND, 0)
        sizer_roi_tree.Add(self.tree_ctrl_roi, 1, wx.ALL | wx.EXPAND, 0)
        self.panel_roi_tree.SetSizer(sizer_roi_tree)
        sizer_roi_map.Add(self.panel_roi_tree, 1, wx.EXPAND, 0)
        sizer_roi_map.Add(self.checkbox_include_uncategorized, 0, wx.EXPAND | wx.BOTTOM, 15)

        self.label['physician_roi'] = wx.StaticText(self, wx.ID_ANY, "Physician's ROI Label:")
        sizer_physician_roi.Add(self.label['physician_roi'], 0, 0, 0)
        sizer_physician_roi.Add(self.input_roi['physician'], 0, wx.EXPAND, 0)

        self.label['roi_type'] = wx.StaticText(self, wx.ID_ANY, "ROI Type:")
        sizer_roi_type.Add(self.label['roi_type'], 0, 0, 0)
        sizer_roi_type.Add(self.input_roi['type'], 0, wx.EXPAND, 0)

        sizer_selected_roi.Add(sizer_physician_roi, 1, wx.ALL | wx.EXPAND, 5)
        sizer_selected_roi.Add(sizer_roi_type, 1, wx.ALL | wx.EXPAND, 5)

        sizer_roi_map.Add(sizer_selected_roi, 0, wx.EXPAND, 0)
        sizer_roi_map.Add(self.button_apply_roi, 0, wx.ALL | wx.EXPAND, 5)
        sizer_roi_map_wrapper.Add(sizer_roi_map, 1, wx.ALL | wx.EXPAND, 10)

        sizer_main.Add(sizer_roi_map_wrapper, 1, wx.EXPAND, 0)
        sizer_wrapper.Add(sizer_main, 1, wx.EXPAND, 0)

        sizer_buttons.Add(self.button_import, 0, wx.ALL, 5)
        sizer_buttons.Add(self.button_cancel, 0, wx.ALL, 5)
        sizer_wrapper.Add(sizer_buttons, 0, wx.ALIGN_RIGHT | wx.BOTTOM | wx.LEFT | wx.RIGHT, 10)

        self.SetSizer(sizer_wrapper)
        self.Layout()
        self.Center()

    def parse_directory(self):
        self.gauge.Show()
        file_count = self.dicom_dir.file_count
        self.dicom_dir.initialize_file_tree_root()
        self.tree_ctrl_import.Expand(self.dicom_dir.root_files)
        while self.dicom_dir.current_index < file_count:
            self.dicom_dir.append_next_file_to_tree()
            self.gauge.SetValue(int(100 * self.dicom_dir.current_index / file_count))
            self.update_progress_message()
            self.tree_ctrl_import.ExpandAll()
            wx.Yield()
        self.gauge.Hide()

    def on_browse(self, evt):
        self.parsed_dicom_data = {}
        for key in list(self.global_plan_over_rides):
            self.global_plan_over_rides[key] = {'value': None, 'only_if_missing': False}
        self.clear_plan_data()
        self.tree_ctrl_roi.DeleteChildren(self.dicom_dir.root_rois)
        starting_dir = self.text_ctrl_directory.GetValue()
        if starting_dir == '':
            starting_dir = self.start_path
        if not isdir(starting_dir):
            starting_dir = ""
        dlg = wx.DirDialog(self, "Select inbox directory", starting_dir, wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.text_ctrl_directory.SetValue(dlg.GetPath())
            self.dicom_dir = DICOM_Importer(self.text_ctrl_directory.GetValue(), self.tree_ctrl_import,
                                            self.tree_ctrl_roi, self.tree_ctrl_roi_root,
                                            search_subfolders=self.checkbox_subfolders.GetValue())
            self.parse_directory()
        dlg.Destroy()

    def update_progress_message(self):
        self.label_progress.SetLabelText("Progress: %s Patients - %s Studies - %s Files" %
                                         (self.dicom_dir.count['patient'],
                                          self.dicom_dir.count['study'],
                                          self.dicom_dir.count['file']))

    def on_file_tree_select(self, evt):
        uid = self.get_file_tree_item_uid(evt.GetItem())
        if uid is not None:
            if uid != self.selected_uid:
                self.selected_uid = uid
                wait = wx.BusyCursor()
                self.dicom_dir.rebuild_tree_ctrl_rois(uid)
                self.tree_ctrl_roi.ExpandAll()
                if uid not in list(self.parsed_dicom_data):
                    file_paths = self.dicom_dir.dicom_file_paths[uid]
                    self.parsed_dicom_data[uid] = DICOM_Parser(plan=file_paths['rtplan']['file_path'],
                                                               structure=file_paths['rtstruct']['file_path'],
                                                               dose=file_paths['rtdose']['file_path'],
                                                               global_plan_over_rides=self.global_plan_over_rides)
                data = self.parsed_dicom_data[uid]

                self.input['mrn'].SetValue(data.mrn)
                self.input['study_instance_uid'].SetValue(data.study_instance_uid)
                if data.birth_date is None or data.birth_date == '':
                    self.input['birth_date'].SetValue('')
                else:
                    self.input['birth_date'].SetValue(datetime_to_date_string(data.birth_date))
                if data.sim_study_date is None or data.sim_study_date == '':
                    self.input['sim_study_date'].SetValue('')
                else:
                    self.input['sim_study_date'].SetValue(datetime_to_date_string(data.sim_study_date))
                self.input['physician'].SetValue(data.physician)
                self.input['tx_site'].SetValue(data.tx_site)
                self.input['rx_dose'].SetValue(str(data.rx_dose))
                self.dicom_dir.check_mapped_rois(data.physician)
                del wait
                self.enable_inputs()
        else:
            self.clear_plan_data()
            self.disable_inputs()
            self.selected_uid = None
            self.tree_ctrl_roi.DeleteChildren(self.dicom_dir.root_rois)

    def on_roi_tree_select(self, evt):
        self.selected_roi = self.get_roi_tree_item_name(evt.GetItem())
        self.update_roi_inputs()

    def update_roi_inputs(self):
        physician = self.input['physician'].GetValue()
        if self.selected_roi and self.roi_map.is_physician(physician):
            physician_roi = self.roi_map.get_physician_roi(physician, self.selected_roi)
            roi_type = self.dicom_dir.roi_name_map[self.selected_roi]['type']
            self.input_roi['physician'].SetValue(physician_roi)
            self.input_roi['type'].SetValue(roi_type)
        else:
            self.input_roi['physician'].SetValue('')
            self.input_roi['type'].SetValue('')

    def clear_plan_data(self):
        for input_obj in self.input.values():
            input_obj.SetValue('')

        self.reset_label_colors()

    def get_file_tree_item_uid(self, item):

        selected_mrn, selected_uid = None, None
        for mrn, node in self.dicom_dir.patient_nodes.items():
            if item == node:
                selected_uid = list(self.dicom_dir.file_tree[mrn])[0]
                break

        if selected_uid is None:
            for uid, node in self.dicom_dir.study_nodes.items():
                if item == node:
                    selected_uid = uid
                    break

        return selected_uid

    def get_roi_tree_item_name(self, item):
        for name, node in self.dicom_dir.roi_nodes.items():
            if item == node:
                return name
        return None

    def on_mrn_change(self, evt):
        self.update_label_text_color('mrn')

    def on_uid_change(self, evt):
        self.update_label_text_color('study_instance_uid')

    def on_birth_date_change(self, evt):
        self.update_label_text_color('birth_date')

    def on_sim_study_date_change(self, evt):
        self.update_label_text_color('sim_study_date')

    def on_physician_change(self, evt):
        self.update_label_text_color('physician')
        self.update_physician_roi_choices()
        physician = self.input['physician'].GetValue()
        if physician:
            self.enable_roi_inputs()
        else:
            self.disable_roi_inputs()

        self.update_roi_inputs()
        self.dicom_dir.check_mapped_rois(physician)

    def on_tx_site_change(self, evt):
        self.update_label_text_color('tx_site')

    def on_rx_change(self, evt):
        self.update_label_text_color('rx_dose')

    def update_label_text_color(self, key):
        red_value = [255, 0][self.input[key].GetValue() != '']
        self.label[key].SetForegroundColour(wx.Colour(red_value, 0, 0))

    def reset_label_colors(self):
        for label in self.label.values():
            label.SetForegroundColour(wx.Colour(0, 0, 0))

    def disable_inputs(self):
        for input_obj in self.input.values():
            input_obj.Disable()
        self.button_apply_plan_data.Disable()

    def enable_inputs(self):
        for input_obj in self.input.values():
            input_obj.Enable()
        self.button_apply_plan_data.Enable()

    def disable_roi_inputs(self):
        for input_obj in self.input_roi.values():
            input_obj.Disable()
        self.button_apply_roi.Disable()

    def enable_roi_inputs(self):
        for input_obj in self.input_roi.values():
            input_obj.Enable()
        self.button_apply_roi.Enable()

    def update_physician_roi_choices(self):
        physician = self.input['physician'].GetValue()
        if self.roi_map.is_physician(physician):
            choices = self.roi_map.get_physician_rois(physician)
        else:
            choices = []
        self.input_roi['physician'].Clear()
        self.input_roi['physician'].Append(choices)

    def on_apply_plan(self, evt):
        over_rides = self.parsed_dicom_data[self.selected_uid].plan_over_rides
        for key in list(over_rides):
            value = self.input[key].GetValue()
            if 'date' in key:
                over_rides[key] = self.validate_date(value)
            elif key == 'rx_dose':
                over_rides[key] = self.validate_dose(value)
            else:
                if not value:
                    value = None
                over_rides[key] = value

            # Apply all
            if "%s_1" % key in list(self.checkbox):
                if self.checkbox["%s_1" % key].IsChecked():
                    self.global_plan_over_rides[key]['value'] = value
                    self.global_plan_over_rides[key]['only_if_missing'] = self.checkbox["%s_2" % key].IsChecked()

        self.clear_plan_check_boxes()

    def on_apply_roi(self, evt):
        over_rides = self.parsed_dicom_data[self.selected_uid].roi_over_rides
        for key in list(self.input_roi):
            over_rides[self.selected_roi][key] = self.input_roi[key].GetValue()

    def validate_date(self, date):
        try:
            dt = parse_date(date)
            truncated = datetime_obj(dt.year, dt.month, dt.day)
            return str(truncated).replace('-', '')
        except:
            return None

    def validate_dose(self, dose):
        try:
            return float(dose)
        except:
            return None

    def is_uid_valid(self, uid):
        cnx = DVH_SQL()
        valid_uid = not cnx.is_study_instance_uid_in_table('Plans', uid)
        cnx.close()
        if valid_uid:
            return True
        return False

    def clear_plan_check_boxes(self):
        for checkbox in self.checkbox.values():
            checkbox.SetValue(False)

    def on_check_apply_all(self, evt):
        for key in ['birth_date', 'sim_study_date', 'physician', 'tx_site', 'rx_dose']:
            if self.checkbox["%s_1" % key].GetId() == evt.GetId():
                if not self.checkbox["%s_1" % key].IsChecked():
                    self.checkbox["%s_2" % key].SetValue(False)
                return
            if self.checkbox["%s_2" % key].GetId() == evt.GetId():
                if self.checkbox["%s_2" % key].IsChecked():
                    self.checkbox["%s_1" % key].SetValue(True)
                return