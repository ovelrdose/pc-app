import { createBrowserRouter } from 'react-router-dom';

import { AppLayout } from '../components/AppLayout';
import { NotFoundPage } from '../components/NotFoundPage';
import { BuildPage } from '../features/build/BuildPage';
import { ComparePage } from '../features/compare/ComparePage';
import { HomePage } from '../features/home/HomePage';
import { ResultsPage } from '../features/results/ResultsPage';
import { WizardPage } from '../features/wizard/WizardPage';

export const routes = [
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'wizard', element: <WizardPage /> },
      { path: 'consultations/:id', element: <ResultsPage /> },
      { path: 'builds/:id', element: <BuildPage /> },
      { path: 'compare', element: <ComparePage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
