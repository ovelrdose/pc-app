import type { components } from './generated/schema';

/** Псевдонимы сгенерированных типов API (сами типы правятся только генератором). */
type Schemas = components['schemas'];

export type AlternativeOut = Schemas['AlternativeOut'];
export type BuildDetail = Schemas['BuildDetail'];
export type BuildItemOut = Schemas['BuildItemOut'];
export type BuildSummary = Schemas['BuildSummary'];
export type Category = Schemas['Category'];
export type CompareOut = Schemas['CompareOut'];
export type CompromiseOut = Schemas['CompromiseOut'];
export type ComponentOut = Schemas['ComponentOut'];
export type ConsultationOut = Schemas['ConsultationOut'];
export type EditKind = Schemas['EditKind'];
export type ExplanationOut = Schemas['ExplanationOut'];
export type FpsOut = Schemas['FpsOut'];
export type GoalOut = Schemas['GoalOut'];
export type HypothesisOut = Schemas['HypothesisOut'];
export type HypothesisRequest = Schemas['HypothesisRequest'];
export type InfeasibleOut = Schemas['InfeasibleOut'];
export type IssueOut = Schemas['IssueOut'];
export type ItemChangeOut = Schemas['ItemChangeOut'];
export type ModificationOut = Schemas['ModificationOut'];
export type ModificationRequest = Schemas['ModificationRequest'];
export type NeedInputOut = Schemas['NeedInputOut'];
export type PerformanceOut = Schemas['PerformanceOut'];
export type ProofNodeOut = Schemas['ProofNodeOut'];
export type QuestionOut = Schemas['QuestionOut'];
export type QuestionnaireOut = Schemas['QuestionnaireOut'];
export type Tier = Schemas['Tier'];
export type WhyNotOut = Schemas['WhyNotOut'];
export type AppOut = Schemas['AppOut'];
export type BenchmarkOut = Schemas['BenchmarkOut'];
export type OptionOut = Schemas['OptionOut'];
export type PreferenceOut = Schemas['PreferenceOut'];
export type ReasoningStepOut = Schemas['ReasoningStepOut'];
export type RelaxationOut = Schemas['RelaxationOut'];
export type StepOut = Schemas['StepOut'];
export type OwnedComponentOut = Schemas['OwnedComponentOut'];
export type UserOut = Schemas['UserOut'];
export type UserRole = Schemas['UserRole'];
export type FrameOut = Schemas['FrameOut'];
export type ComponentPage = Schemas['ComponentPage'];
export type ComponentPatchIn = Schemas['ComponentPatchIn'];
export type ComponentStatus = Schemas['ComponentStatus'];
export type ComponentSource = Schemas['ComponentSource'];
export type CatalogImportOut = Schemas['CatalogImportOut'];
/** Тело создания/полной замены компонента: фрейм категории с дискриминатором `category`. */
export type ComponentFrame =
  | Schemas['CPU']
  | Schemas['Motherboard']
  | Schemas['RAM']
  | Schemas['GPU']
  | Schemas['SSD']
  | Schemas['HDD']
  | Schemas['PSU']
  | Schemas['Case']
  | Schemas['CPUCooler']
  | Schemas['CaseFan'];
export type TokenOut = Schemas['TokenOut'];
export type RefreshOut = Schemas['RefreshOut'];
export type GuestSessionOut = Schemas['GuestSessionOut'];
export type MeBuildsOut = Schemas['MeBuildsOut'];
export type SavedBuildOut = Schemas['SavedBuildOut'];

// --- Админка базы знаний (этап 9, пакет В) ---
export type Rule = Schemas['Rule'];
export type RuleOut = Schemas['RuleOut'];
export type RulePage = Schemas['RulePage'];
export type RuleDetailOut = Schemas['RuleDetailOut'];
export type RuleRevisionOut = Schemas['RuleRevisionOut'];
export type RuleKind = Schemas['RuleKind'];
export type RuleOrigin = Schemas['RuleOrigin'];
export type Op = Schemas['Op'];
export type Scalar = Schemas['Scalar'];
export type LiteralValue = Schemas['LiteralValue'];
export type GoalRef = Schemas['GoalRef'];
export type AllCondition = Schemas['AllCondition'];
export type AnyCondition = Schemas['AnyCondition'];
export type NotCondition = Schemas['NotCondition'];
export type FactCondition = Schemas['FactCondition'];
export type ExprCondition = Schemas['ExprCondition'];
export type GoalCondition = Schemas['GoalCondition'];
/** Узел дерева условий правила (все виды листьев и групп). */
export type ConditionNode =
  AllCondition | AnyCondition | NotCondition | FactCondition | ExprCondition | GoalCondition;
export type RuleAction =
  | Schemas['AssertAction']
  | Schemas['RetractAction']
  | Schemas['RejectAction']
  | Schemas['PreferAction']
  | Schemas['WarnAction']
  | Schemas['ErrorAction']
  | Schemas['SuggestAction'];
export type VocabularyOut = Schemas['VocabularyOut'];
export type ValidateReportOut = Schemas['ValidateReportOut'];
/** Лёгкий статус черновика: контрольная сумма, совпадение со снимком, число правил. */
export type KbStatusOut = Schemas['KbStatusOut'];
export type GoldenReportOut = Schemas['GoldenReportOut'];
export type PublishOut = Schemas['PublishOut'];
export type SnapshotOut = Schemas['SnapshotOut'];
export type RegenerateOut = Schemas['RegenerateOut'];
export type RuleTestIn = Schemas['RuleTestIn'];
export type RuleTestOut = Schemas['RuleTestOut'];
export type RuleTestActionOut = Schemas['RuleTestActionOut'];
export type RuleTestFactOut = Schemas['RuleTestFactOut'];

// --- Админка пользователей (этап 9, пакет В) ---
export type UserAdminOut = Schemas['UserAdminOut'];
export type UserAdminPage = Schemas['UserAdminPage'];
export type UserPatchIn = Schemas['UserPatchIn'];
