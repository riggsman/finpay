import { Navigate, Route, Routes } from "react-router-dom";
import Landing from "./pages/Landing";
import Register from "./pages/Register";
import Login from "./pages/Login";
import ForgotPassword from "./pages/ForgotPassword";
import Dashboard from "./pages/Dashboard";
import Wallet from "./pages/Wallet";
import Profile from "./pages/Profile";
import Activity from "./pages/Activity";
import Notifications from "./pages/Notifications";
import Services from "./pages/Services";
import ServicePay from "./pages/ServicePay";
import WalletAction from "./pages/WalletAction";
import Security from "./pages/Security";
import LimitIncrease from "./pages/LimitIncrease";
import History from "./pages/History";
import TransactionDetail from "./pages/TransactionDetail";
import Kyc from "./pages/Kyc";
import Support from "./pages/Support";
import TicketDetail from "./pages/TicketDetail";
import Requests from "./pages/Requests";
import AdminLogin from "./pages/AdminLogin";
import BackOffice from "./pages/BackOffice";
import ProtectedRoute from "./routes/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/register" element={<Register />} />
      <Route path="/login" element={<Login />} />
      <Route path="/admin/login" element={<AdminLogin />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/notifications" element={<ProtectedRoute><Notifications /></ProtectedRoute>} />
      <Route path="/wallet" element={<ProtectedRoute><Wallet /></ProtectedRoute>} />
      <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
      <Route path="/profile/activity" element={<ProtectedRoute><Activity /></ProtectedRoute>} />
      <Route path="/services" element={<ProtectedRoute><Services /></ProtectedRoute>} />
      <Route path="/services/:category" element={<ProtectedRoute><ServicePay /></ProtectedRoute>} />
      <Route path="/wallet/add" element={<ProtectedRoute><WalletAction mode="deposit" /></ProtectedRoute>} />
      <Route path="/wallet/send" element={<ProtectedRoute><WalletAction mode="send" /></ProtectedRoute>} />
      <Route path="/wallet/withdraw" element={<ProtectedRoute><WalletAction mode="withdraw" /></ProtectedRoute>} />
      <Route path="/wallet/requests" element={<ProtectedRoute><Requests /></ProtectedRoute>} />
      <Route path="/security" element={<ProtectedRoute><Security /></ProtectedRoute>} />
      <Route path="/security/limits" element={<ProtectedRoute><LimitIncrease /></ProtectedRoute>} />
      <Route path="/transactions" element={<ProtectedRoute><History /></ProtectedRoute>} />
      <Route path="/transactions/:id" element={<ProtectedRoute><TransactionDetail /></ProtectedRoute>} />
      <Route path="/kyc" element={<ProtectedRoute><Kyc /></ProtectedRoute>} />
      <Route path="/support" element={<ProtectedRoute><Support /></ProtectedRoute>} />
      <Route path="/support/tickets/:id" element={<ProtectedRoute><TicketDetail /></ProtectedRoute>} />
      <Route path="/admin" element={<ProtectedRoute adminOnly><BackOffice /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
