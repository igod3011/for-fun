import React, { useMemo, useState } from 'react';
import {
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
  Pressable,
} from 'react-native';

const tabs = [
  { key: 'schedule', label: 'Lịch' },
  { key: 'reminders', label: 'Nhắc nhở' },
  { key: 'notes', label: 'Ghi nhớ' },
  { key: 'expenses', label: 'Chi tiêu' },
  { key: 'tasks', label: 'Công việc' },
];

const initialSchedule = [
  { id: 'sc1', title: 'Họp sprint', time: '09:00', date: 'Thứ hai', detail: 'Chốt mục tiêu tuần' },
  { id: 'sc2', title: 'Đón con', time: '17:30', date: 'Thứ ba', detail: 'Tại cổng trường' },
];

const initialReminders = [
  { id: 'rm1', title: 'Uống nước', when: 'Mỗi 2 giờ', done: false },
  { id: 'rm2', title: 'Thanh toán điện', when: 'Ngày 25 hàng tháng', done: true },
];

const initialNotes = [
  { id: 'nt1', title: 'Ý tưởng', content: 'Gom mọi việc cá nhân trong một app duy nhất.' },
  { id: 'nt2', title: 'Mua sắm', content: 'Sữa, trái cây, pin dự phòng.' },
];

const initialExpenses = [
  { id: 'ex1', title: 'Ăn trưa', amount: 65000, category: 'Ăn uống' },
  { id: 'ex2', title: 'Gửi xe', amount: 10000, category: 'Di chuyển' },
  { id: 'ex3', title: 'Netflix', amount: 180000, category: 'Giải trí' },
];

const initialTasks = [
  { id: 'tk1', title: 'Hoàn thiện proposal', priority: 'Cao', done: false },
  { id: 'tk2', title: 'Gọi khách hàng', priority: 'Trung bình', done: true },
  { id: 'tk3', title: 'Chuẩn bị báo cáo', priority: 'Cao', done: false },
];

const money = new Intl.NumberFormat('vi-VN');

const SectionTitle = ({ title, subtitle }) => (
  <View style={styles.sectionHeader}>
    <Text style={styles.sectionTitle}>{title}</Text>
    <Text style={styles.sectionSubtitle}>{subtitle}</Text>
  </View>
);

const StatCard = ({ label, value, accent }) => (
  <View style={[styles.statCard, { borderColor: accent }]}>
    <Text style={styles.statLabel}>{label}</Text>
    <Text style={styles.statValue}>{value}</Text>
  </View>
);

const RowCard = ({ title, subtitle, right, highlighted }) => (
  <View style={[styles.rowCard, highlighted && styles.rowCardHighlighted]}>
    <View style={styles.rowCardBody}>
      <Text style={styles.rowCardTitle}>{title}</Text>
      <Text style={styles.rowCardSubtitle}>{subtitle}</Text>
    </View>
    {right ? <View>{right}</View> : null}
  </View>
);

export default function App() {
  const [activeTab, setActiveTab] = useState('schedule');
  const [schedule, setSchedule] = useState(initialSchedule);
  const [reminders, setReminders] = useState(initialReminders);
  const [notes, setNotes] = useState(initialNotes);
  const [expenses, setExpenses] = useState(initialExpenses);
  const [tasks, setTasks] = useState(initialTasks);

  const [scheduleForm, setScheduleForm] = useState({ title: '', time: '', date: '' });
  const [reminderForm, setReminderForm] = useState({ title: '', when: '' });
  const [noteForm, setNoteForm] = useState({ title: '', content: '' });
  const [expenseForm, setExpenseForm] = useState({ title: '', amount: '', category: '' });
  const [taskForm, setTaskForm] = useState({ title: '', priority: '' });

  const totalExpense = useMemo(
    () => expenses.reduce((sum, item) => sum + Number(item.amount || 0), 0),
    [expenses]
  );
  const openTasks = useMemo(() => tasks.filter((item) => !item.done).length, [tasks]);
  const doneReminders = useMemo(() => reminders.filter((item) => item.done).length, [reminders]);

  const addSchedule = () => {
    if (!scheduleForm.title || !scheduleForm.time || !scheduleForm.date) return;
    setSchedule((current) => [
      {
        id: `sc-${Date.now()}`,
        title: scheduleForm.title,
        time: scheduleForm.time,
        date: scheduleForm.date,
        detail: 'Tạo mới từ ứng dụng',
      },
      ...current,
    ]);
    setScheduleForm({ title: '', time: '', date: '' });
  };

  const addReminder = () => {
    if (!reminderForm.title || !reminderForm.when) return;
    setReminders((current) => [
      { id: `rm-${Date.now()}`, title: reminderForm.title, when: reminderForm.when, done: false },
      ...current,
    ]);
    setReminderForm({ title: '', when: '' });
  };

  const addNote = () => {
    if (!noteForm.title || !noteForm.content) return;
    setNotes((current) => [
      { id: `nt-${Date.now()}`, title: noteForm.title, content: noteForm.content },
      ...current,
    ]);
    setNoteForm({ title: '', content: '' });
  };

  const addExpense = () => {
    if (!expenseForm.title || !expenseForm.amount || !expenseForm.category) return;
    setExpenses((current) => [
      {
        id: `ex-${Date.now()}`,
        title: expenseForm.title,
        amount: Number(expenseForm.amount),
        category: expenseForm.category,
      },
      ...current,
    ]);
    setExpenseForm({ title: '', amount: '', category: '' });
  };

  const addTask = () => {
    if (!taskForm.title || !taskForm.priority) return;
    setTasks((current) => [
      { id: `tk-${Date.now()}`, title: taskForm.title, priority: taskForm.priority, done: false },
      ...current,
    ]);
    setTaskForm({ title: '', priority: '' });
  };

  const toggleReminder = (id) => {
    setReminders((current) =>
      current.map((item) => (item.id === id ? { ...item, done: !item.done } : item))
    );
  };

  const toggleTask = (id) => {
    setTasks((current) => current.map((item) => (item.id === id ? { ...item, done: !item.done } : item)));
  };

  const renderOverview = () => (
    <View style={styles.overviewCard}>
      <Text style={styles.overviewEyebrow}>One app for everything</Text>
      <Text style={styles.overviewTitle}>LifeHub</Text>
      <Text style={styles.overviewText}>
        Quản lý lịch, nhắc nhở, ghi chú, chi tiêu và công việc trong cùng một trải nghiệm mobile.
      </Text>
      <View style={styles.statsGrid}>
        <StatCard label="Lịch tuần" value={`${schedule.length} mục`} accent="#8b5cf6" />
        <StatCard label="Nhắc nhở xong" value={`${doneReminders}/${reminders.length}`} accent="#0ea5e9" />
        <StatCard label="Chi tiêu" value={`${money.format(totalExpense)}đ`} accent="#f97316" />
        <StatCard label="Việc đang mở" value={`${openTasks} việc`} accent="#22c55e" />
      </View>
    </View>
  );

  const renderSchedule = () => (
    <View>
      <SectionTitle title="Lịch cá nhân" subtitle="Theo dõi sự kiện quan trọng trong tuần." />
      <View style={styles.formCard}>
        <TextInput
          placeholder="Tên sự kiện"
          placeholderTextColor="#94a3b8"
          style={styles.input}
          value={scheduleForm.title}
          onChangeText={(text) => setScheduleForm((current) => ({ ...current, title: text }))}
        />
        <View style={styles.inlineInputs}>
          <TextInput
            placeholder="Giờ"
            placeholderTextColor="#94a3b8"
            style={[styles.input, styles.inlineInput]}
            value={scheduleForm.time}
            onChangeText={(text) => setScheduleForm((current) => ({ ...current, time: text }))}
          />
          <TextInput
            placeholder="Ngày"
            placeholderTextColor="#94a3b8"
            style={[styles.input, styles.inlineInput]}
            value={scheduleForm.date}
            onChangeText={(text) => setScheduleForm((current) => ({ ...current, date: text }))}
          />
        </View>
        <Pressable style={styles.primaryButton} onPress={addSchedule}>
          <Text style={styles.primaryButtonText}>Thêm lịch</Text>
        </Pressable>
      </View>
      {schedule.map((item) => (
        <RowCard
          key={item.id}
          title={item.title}
          subtitle={`${item.date} • ${item.time} • ${item.detail}`}
          right={<Text style={styles.tag}>{item.time}</Text>}
        />
      ))}
    </View>
  );

  const renderReminders = () => (
    <View>
      <SectionTitle title="Nhắc nhở" subtitle="Không bỏ quên việc nhỏ nhưng quan trọng." />
      <View style={styles.formCard}>
        <TextInput
          placeholder="Nội dung nhắc nhở"
          placeholderTextColor="#94a3b8"
          style={styles.input}
          value={reminderForm.title}
          onChangeText={(text) => setReminderForm((current) => ({ ...current, title: text }))}
        />
        <TextInput
          placeholder="Khi nào?"
          placeholderTextColor="#94a3b8"
          style={styles.input}
          value={reminderForm.when}
          onChangeText={(text) => setReminderForm((current) => ({ ...current, when: text }))}
        />
        <Pressable style={styles.primaryButton} onPress={addReminder}>
          <Text style={styles.primaryButtonText}>Tạo nhắc nhở</Text>
        </Pressable>
      </View>
      {reminders.map((item) => (
        <Pressable key={item.id} onPress={() => toggleReminder(item.id)}>
          <RowCard
            title={item.title}
            subtitle={item.when}
            highlighted={item.done}
            right={<Text style={[styles.statusPill, item.done && styles.statusPillDone]}>{item.done ? 'Xong' : 'Mở'}</Text>}
          />
        </Pressable>
      ))}
    </View>
  );

  const renderNotes = () => (
    <View>
      <SectionTitle title="Ghi nhớ nhanh" subtitle="Lưu ý tưởng, checklist và thông tin cần nhớ." />
      <View style={styles.formCard}>
        <TextInput
          placeholder="Tiêu đề"
          placeholderTextColor="#94a3b8"
          style={styles.input}
          value={noteForm.title}
          onChangeText={(text) => setNoteForm((current) => ({ ...current, title: text }))}
        />
        <TextInput
          placeholder="Nội dung ghi chú"
          placeholderTextColor="#94a3b8"
          style={[styles.input, styles.multilineInput]}
          multiline
          value={noteForm.content}
          onChangeText={(text) => setNoteForm((current) => ({ ...current, content: text }))}
        />
        <Pressable style={styles.primaryButton} onPress={addNote}>
          <Text style={styles.primaryButtonText}>Lưu ghi chú</Text>
        </Pressable>
      </View>
      {notes.map((item) => (
        <RowCard key={item.id} title={item.title} subtitle={item.content} />
      ))}
    </View>
  );

  const renderExpenses = () => (
    <View>
      <SectionTitle title="Quản lý chi tiêu" subtitle="Nắm ngay các khoản chi trong ngày và tháng." />
      <View style={styles.formCard}>
        <TextInput
          placeholder="Khoản chi"
          placeholderTextColor="#94a3b8"
          style={styles.input}
          value={expenseForm.title}
          onChangeText={(text) => setExpenseForm((current) => ({ ...current, title: text }))}
        />
        <View style={styles.inlineInputs}>
          <TextInput
            placeholder="Số tiền"
            placeholderTextColor="#94a3b8"
            keyboardType="numeric"
            style={[styles.input, styles.inlineInput]}
            value={expenseForm.amount}
            onChangeText={(text) => setExpenseForm((current) => ({ ...current, amount: text }))}
          />
          <TextInput
            placeholder="Danh mục"
            placeholderTextColor="#94a3b8"
            style={[styles.input, styles.inlineInput]}
            value={expenseForm.category}
            onChangeText={(text) => setExpenseForm((current) => ({ ...current, category: text }))}
          />
        </View>
        <Pressable style={styles.primaryButton} onPress={addExpense}>
          <Text style={styles.primaryButtonText}>Ghi nhận chi tiêu</Text>
        </Pressable>
      </View>
      <View style={styles.summaryBanner}>
        <Text style={styles.summaryBannerLabel}>Tổng chi đã lưu</Text>
        <Text style={styles.summaryBannerValue}>{money.format(totalExpense)}đ</Text>
      </View>
      {expenses.map((item) => (
        <RowCard
          key={item.id}
          title={item.title}
          subtitle={item.category}
          right={<Text style={styles.expenseAmount}>{money.format(item.amount)}đ</Text>}
        />
      ))}
    </View>
  );

  const renderTasks = () => (
    <View>
      <SectionTitle title="Quản lý công việc" subtitle="Theo dõi ưu tiên và tiến độ hoàn thành." />
      <View style={styles.formCard}>
        <TextInput
          placeholder="Tên công việc"
          placeholderTextColor="#94a3b8"
          style={styles.input}
          value={taskForm.title}
          onChangeText={(text) => setTaskForm((current) => ({ ...current, title: text }))}
        />
        <TextInput
          placeholder="Ưu tiên: Cao / Trung bình / Thấp"
          placeholderTextColor="#94a3b8"
          style={styles.input}
          value={taskForm.priority}
          onChangeText={(text) => setTaskForm((current) => ({ ...current, priority: text }))}
        />
        <Pressable style={styles.primaryButton} onPress={addTask}>
          <Text style={styles.primaryButtonText}>Thêm công việc</Text>
        </Pressable>
      </View>
      {tasks.map((item) => (
        <Pressable key={item.id} onPress={() => toggleTask(item.id)}>
          <RowCard
            title={item.title}
            subtitle={`Ưu tiên: ${item.priority}`}
            highlighted={item.done}
            right={<Text style={[styles.statusPill, item.done && styles.statusPillDone]}>{item.done ? 'Done' : 'Todo'}</Text>}
          />
        </Pressable>
      ))}
    </View>
  );

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar barStyle="light-content" />
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
        <Text style={styles.appLabel}>Ứng dụng all-in-one</Text>
        <Text style={styles.appTitle}>Tổ chức cuộc sống trong 1 app mobile</Text>
        <Text style={styles.appSubtitle}>
          Chạm để chuyển khu vực và thêm dữ liệu mẫu ngay trên giao diện.
        </Text>

        {renderOverview()}

        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabList}>
          {tabs.map((tab) => (
            <Pressable
              key={tab.key}
              onPress={() => setActiveTab(tab.key)}
              style={[styles.tabButton, activeTab === tab.key && styles.tabButtonActive]}
            >
              <Text style={[styles.tabButtonText, activeTab === tab.key && styles.tabButtonTextActive]}>
                {tab.label}
              </Text>
            </Pressable>
          ))}
        </ScrollView>

        {activeTab === 'schedule' && renderSchedule()}
        {activeTab === 'reminders' && renderReminders()}
        {activeTab === 'notes' && renderNotes()}
        {activeTab === 'expenses' && renderExpenses()}
        {activeTab === 'tasks' && renderTasks()}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#020617',
  },
  container: {
    flex: 1,
    backgroundColor: '#020617',
  },
  content: {
    padding: 20,
    paddingBottom: 48,
    gap: 16,
  },
  appLabel: {
    color: '#38bdf8',
    fontSize: 14,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginTop: 8,
  },
  appTitle: {
    color: '#f8fafc',
    fontSize: 30,
    fontWeight: '800',
    marginTop: 8,
  },
  appSubtitle: {
    color: '#cbd5e1',
    fontSize: 15,
    lineHeight: 22,
    marginTop: 8,
    marginBottom: 4,
  },
  overviewCard: {
    backgroundColor: '#111827',
    borderRadius: 24,
    padding: 20,
    borderWidth: 1,
    borderColor: '#1f2937',
    gap: 10,
  },
  overviewEyebrow: {
    color: '#a78bfa',
    fontSize: 13,
    fontWeight: '700',
  },
  overviewTitle: {
    color: '#f8fafc',
    fontSize: 28,
    fontWeight: '800',
  },
  overviewText: {
    color: '#cbd5e1',
    lineHeight: 22,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginTop: 4,
  },
  statCard: {
    width: '47%',
    backgroundColor: '#0f172a',
    borderRadius: 18,
    padding: 14,
    borderWidth: 1,
  },
  statLabel: {
    color: '#94a3b8',
    fontSize: 13,
    marginBottom: 6,
  },
  statValue: {
    color: '#f8fafc',
    fontSize: 18,
    fontWeight: '700',
  },
  tabList: {
    marginVertical: 6,
  },
  tabButton: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 999,
    backgroundColor: '#0f172a',
    marginRight: 10,
    borderWidth: 1,
    borderColor: '#1e293b',
  },
  tabButtonActive: {
    backgroundColor: '#38bdf8',
    borderColor: '#38bdf8',
  },
  tabButtonText: {
    color: '#cbd5e1',
    fontWeight: '600',
  },
  tabButtonTextActive: {
    color: '#082f49',
  },
  sectionHeader: {
    gap: 4,
    marginBottom: 12,
    marginTop: 4,
  },
  sectionTitle: {
    fontSize: 24,
    fontWeight: '800',
    color: '#f8fafc',
  },
  sectionSubtitle: {
    color: '#94a3b8',
    lineHeight: 20,
  },
  formCard: {
    backgroundColor: '#111827',
    borderRadius: 20,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#1f2937',
  },
  input: {
    backgroundColor: '#0f172a',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#1e293b',
    color: '#f8fafc',
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 10,
  },
  inlineInputs: {
    flexDirection: 'row',
    gap: 10,
  },
  inlineInput: {
    flex: 1,
  },
  multilineInput: {
    minHeight: 96,
    textAlignVertical: 'top',
  },
  primaryButton: {
    backgroundColor: '#8b5cf6',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 2,
  },
  primaryButtonText: {
    color: '#f8fafc',
    fontWeight: '700',
    fontSize: 15,
  },
  rowCard: {
    backgroundColor: '#111827',
    borderRadius: 18,
    padding: 16,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#1f2937',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  rowCardHighlighted: {
    borderColor: '#22c55e',
    backgroundColor: '#052e16',
  },
  rowCardBody: {
    flex: 1,
    gap: 4,
  },
  rowCardTitle: {
    color: '#f8fafc',
    fontSize: 16,
    fontWeight: '700',
  },
  rowCardSubtitle: {
    color: '#94a3b8',
    lineHeight: 20,
  },
  tag: {
    color: '#38bdf8',
    fontWeight: '700',
  },
  statusPill: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    overflow: 'hidden',
    backgroundColor: '#172554',
    color: '#93c5fd',
    fontWeight: '700',
  },
  statusPillDone: {
    backgroundColor: '#14532d',
    color: '#86efac',
  },
  summaryBanner: {
    backgroundColor: '#7c2d12',
    borderRadius: 18,
    padding: 16,
    marginBottom: 12,
  },
  summaryBannerLabel: {
    color: '#fdba74',
    marginBottom: 6,
    fontWeight: '600',
  },
  summaryBannerValue: {
    color: '#fff7ed',
    fontSize: 24,
    fontWeight: '800',
  },
  expenseAmount: {
    color: '#fdba74',
    fontWeight: '800',
  },
});
